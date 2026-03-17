import os
import json
import numpy as np
import pandas as pd
import pymysql
import scipy.stats as stats
import shap
from dotenv import load_dotenv

from xgboost import XGBRanker
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression

import warnings
warnings.filterwarnings("ignore")

from modeling.data_joiner import StockDataJoiner
from modeling.feature_selector import FeatureSelector

load_dotenv()

# =========================================================================
# 0. 판다스 날짜 에러 우회 패치
# =========================================================================
original_merge_asof = pd.merge_asof
def patched_merge_asof(left, right, on=None, left_on=None, right_on=None, **kwargs):
    if left_on and right_on:
        left[left_on] = pd.to_datetime(left[left_on]).astype('datetime64[ns]')
        right[right_on] = pd.to_datetime(right[right_on]).astype('datetime64[ns]')
    elif on:
        left[on] = pd.to_datetime(left[on]).astype('datetime64[ns]')
        right[on] = pd.to_datetime(right[on]).astype('datetime64[ns]')
    return original_merge_asof(left, right, on=on, left_on=left_on, right_on=right_on, **kwargs)
pd.merge_asof = patched_merge_asof

# =========================================================================
# 1. 공통 유틸리티
# =========================================================================
def _connect():
    host = os.environ.get('DB_HOST')
    port = int(os.environ.get('DB_PORT'))
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=db_name, connect_timeout=10
    )
    return conn

def zfill6(x):
    return pd.Series(x).astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False).str.strip().str.zfill(6).values[0]

def get_trade_calendar(dates: pd.Series) -> np.ndarray:
    cal = pd.to_datetime(dates, errors="coerce").dropna().unique()
    return np.sort(cal.astype("datetime64[ns]"))

def get_embargo_limit(unique_trading_days: np.ndarray, valid_start_idx: int, horizon_h: int) -> pd.Timestamp:
    embargo_pos = valid_start_idx - horizon_h - 1
    if embargo_pos < 0:
        raise ValueError("[오류] 엠바고를 적용할 만큼 충분한 학습 이력이 없습니다.")
    return pd.to_datetime(unique_trading_days[embargo_pos])

def safe_mean(values, default=0.0):
    return float(np.mean(values)) if len(values) > 0 else default

# =========================================================================
# 2. 평가 및 신뢰도 함수
# =========================================================================
def evaluate_rank_metrics(df_eval: pd.DataFrame, top_k: int = 20, min_stocks: int = 40):
    daily_ic, long_short_spreads, topk_hit_rates, daily_accuracies = [], [], [], []

    for date, group in df_eval.groupby("trade_date"):
        n_stocks = len(group)
        if n_stocks < min_stocks: continue

        ic, _ = stats.spearmanr(group["pred_score"], group["excess_ret"])
        if not np.isnan(ic): daily_ic.append(ic)

        group_sorted = group.sort_values("pred_score", ascending=False)
        k = min(top_k, n_stocks // 2)
        top_mean = group_sorted.head(k)["excess_ret"].mean()
        bottom_mean = group_sorted.tail(k)["excess_ret"].mean()
        long_short_spreads.append(top_mean - bottom_mean)

        hit_rate = (group_sorted.head(k)["excess_ret"] > 0).mean()
        topk_hit_rates.append(hit_rate)

        group = group.copy()
        group["pred_rank"] = group["pred_score"].rank(ascending=False, method="first")
        group["pred_direction"] = (group["pred_rank"] <= (n_stocks / 2)).astype(int)
        group["actual_direction"] = (group["excess_ret"] > 0).astype(int)
        daily_accuracies.append((group["pred_direction"] == group["actual_direction"]).mean())

    return {
        "dir_acc": safe_mean(daily_accuracies) * 100,
        "hit_rate": safe_mean(topk_hit_rates) * 100,
        "rank_ic": safe_mean(daily_ic, default=np.nan),
        "ls_spread": safe_mean(long_short_spreads) * 100,
    }

def build_confidence_scores(df_eval: pd.DataFrame, min_obs: int = 20):
    confidence_records = []
    for ticker, group in df_eval.groupby("ticker"):
        if len(group) < min_obs: continue

        mean_rank_error = group["rank_error"].mean()
        rank_acc_score = (1.0 - mean_rank_error) * 100

        ic = 0
        if group["pred_score"].nunique() > 1 and group["excess_ret"].nunique() > 1:
            ic, _ = stats.spearmanr(group["pred_score"], group["excess_ret"])
            ic = 0 if np.isnan(ic) else ic

        ts_ic_score = max(0, ic * 100)
        raw_conf_score = (rank_acc_score * 0.6) + (ts_ic_score * 0.4)

        shrink = min(1.0, len(group) / 60.0)
        conf_score = shrink * raw_conf_score + (1.0 - shrink) * 50.0

        confidence_records.append({"ticker": ticker, "conf_score": conf_score})
    return pd.DataFrame(confidence_records).set_index("ticker")

# =========================================================================
# 3. 메인 파이프라인
# =========================================================================
def run_long_term_pipeline():
    H_VAL = 189
    print(f"🚀 중장기 예측 모델 파이프라인 가동...")

    joiner = StockDataJoiner()
    selector = FeatureSelector()

    conn = _connect()
    try:
        kospi_df = pd.read_sql("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB", conn)

        # SHAP 분석 시 거시/공통 파생 지표 제외
        macro_df = pd.read_sql("SELECT * FROM MACROECONOMICS_TB LIMIT 1", conn)
        common_df = pd.read_sql("SELECT * FROM COMMON_TB LIMIT 1", conn)
        
        macro_cols = [c for c in macro_df.columns if c not in ['trade_date', 'date']]
        common_cols = [c for c in common_df.columns if c not in ['trade_date', 'date']]
        global_exclude_bases = set(macro_cols + common_cols + ['msci_event'])
    finally:
        conn.close()

    print(f"[1/6] 총 {len(kospi_df)}개 종목 데이터 병합 및 피처 세팅 중...")
    all_dfs = []
    latest_date = None

    for s_name in kospi_df['stock_name']:
        # StockDataJoiner 호출
        df = joiner.get_modeling_dataset(s_name)

        if df is None or len(df) < H_VAL + 30:
            continue
        
        ticker = zfill6([df['ticker'].iloc[0]])
        df['ticker'] = ticker
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        if latest_date is None or df['trade_date'].max() > latest_date:
            latest_date = df['trade_date'].max()

        # FeatureSelector 호출
        df = selector.get_features(df, mode='long')

        all_dfs.append(df)

    if not all_dfs:
        print("❌ 수집된 데이터가 없습니다.")
        return

    df_m = pd.concat(all_dfs, ignore_index=True)
    df_m = df_m.sort_values(["trade_date", "ticker"]).reset_index(drop=True)

    print("[2/6] 추가 지표 및 엠바고 타겟 계산 중...")
    
    # 모멘텀, 외인지배력 별도 계산
    df_m["mom_1m"] = df_m.groupby("ticker")["close"].pct_change(20)
    df_m["mom_1_6"] = df_m.groupby("ticker")["close"].shift(20) / df_m.groupby("ticker")["close"].shift(120) - 1
    df_m["mom_7_12"] = df_m.groupby("ticker")["close"].shift(120) / df_m.groupby("ticker")["close"].shift(250) - 1
    
    df_m["rank_mom_7_12"] = df_m.groupby("trade_date")["mom_7_12"].rank(pct=True)
    df_m["rank_mom_1_6"] = df_m.groupby("trade_date")["mom_1_6"].rank(pct=True)

    if "foreign_net_amt" in df_m.columns and "volume" in df_m.columns:
        df_m["foreign_dominance"] = df_m["foreign_net_amt"] / ((df_m["volume"] * df_m["close"]) + 1)
    else:
        df_m["foreign_dominance"] = np.nan

    # 타겟 생성
    df_m["raw_ret"] = df_m.groupby("ticker")["close"].shift(-H_VAL) / df_m["close"] - 1.0
    df_m["market_median"] = df_m.groupby("trade_date")["raw_ret"].transform("median")
    df_m["excess_ret"] = df_m["raw_ret"] - df_m["market_median"]

    mask_valid_target = df_m["excess_ret"].notna()
    df_m.loc[mask_valid_target, "relevance"] = df_m[mask_valid_target].groupby("trade_date")["excess_ret"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
    )
    df_m["relevance"] = df_m["relevance"].fillna(0).astype(int)

    df_m = df_m.replace([np.inf, -np.inf], np.nan)

    ignore_cols = {"close", "raw_ret", "market_median", "excess_ret", "relevance", "trade_date", "ticker", "stock_name"}
    feats = [c for c in df_m.columns if c not in ignore_cols and pd.api.types.is_numeric_dtype(df_m[c])]
    X_raw = df_m[feats]

    print("[3/6] 엠바고 스플릿 및 XGBRanker 학습 중...")
    unique_trading_days = get_trade_calendar(df_m["trade_date"])
    valid_idx = int(len(unique_trading_days) * 0.8)
    
    valid_start_date = pd.to_datetime(unique_trading_days[valid_idx])
    embargo_limit = get_embargo_limit(unique_trading_days, valid_idx, H_VAL)
    
    valid_dates = unique_trading_days[valid_idx:]
    split_idx = int(len(valid_dates) * 0.5)
    valid_eval_end_date = pd.to_datetime(valid_dates[split_idx - 1])

    train_mask = df_m["trade_date"] <= embargo_limit
    valid_eval_mask = (df_m["trade_date"] >= valid_start_date) & (df_m["trade_date"] <= valid_eval_end_date)
    valid_calib_mask = df_m["trade_date"] > valid_eval_end_date

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    X_train = imputer.fit_transform(X_raw.loc[train_mask])
    y_train_rel = df_m.loc[train_mask, "relevance"].values
    qid_train = pd.factorize(pd.to_datetime(df_m.loc[train_mask, "trade_date"]))[0]

    X_valid_eval = imputer.transform(X_raw.loc[valid_eval_mask])
    y_valid_eval_rel = df_m.loc[valid_eval_mask, "relevance"].values
    qid_valid_eval = pd.factorize(pd.to_datetime(df_m.loc[valid_eval_mask, "trade_date"]))[0]

    ranker = XGBRanker(n_estimators=300, learning_rate=0.03, max_depth=4, objective="rank:pairwise", subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, tree_method='hist')
    ranker.fit(X_train, y_train_rel, qid=qid_train, eval_set=[(X_valid_eval, y_valid_eval_rel)], eval_qid=[qid_valid_eval], verbose=False)

    print("[4/6] 성능 평가 및 기대수익률 캘리브레이션...")
    df_eval = df_m.loc[valid_eval_mask, ["trade_date", "ticker", "excess_ret"]].copy()
    df_eval["pred_score"] = ranker.predict(X_valid_eval)
    metrics = evaluate_rank_metrics(df_eval, top_k=20, min_stocks=40)
    
    df_eval["pred_pct"] = df_eval.groupby("trade_date")["pred_score"].rank(pct=True)
    df_eval["actual_pct"] = df_eval.groupby("trade_date")["excess_ret"].rank(pct=True)
    df_eval["rank_error"] = (df_eval["pred_pct"] - df_eval["actual_pct"]).abs()
    df_stock_conf = build_confidence_scores(df_eval, min_obs=20)

    X_valid_calib = imputer.transform(X_raw.loc[valid_calib_mask])
    excess_ret_calib = df_m.loc[valid_calib_mask, "excess_ret"].values
    pred_scores_calib = ranker.predict(X_valid_calib)
    
    mask_calib = ~np.isnan(excess_ret_calib)
    X_calib_final = pred_scores_calib[mask_calib].reshape(-1, 1)
    y_calib_final = excess_ret_calib[mask_calib]

    # 캘리브레이터 초기화
    calibrator = LinearRegression()
    is_fitted = False

    # 1단계: 최근 데이터로 시도
    if len(y_calib_final) > 50:
        calibrator.fit(X_calib_final, y_calib_final)
        is_fitted = True
    
    # 2단계: 실패 시 과거 데이터로 시도
    if not is_fitted:
        df_eval_clean = df_eval.dropna(subset=["pred_score", "excess_ret"])
        if len(df_eval_clean) > 0:
            calibrator.fit(
                df_eval_clean["pred_score"].values.reshape(-1, 1), 
                df_eval_clean["excess_ret"].values
            )
            is_fitted = True

    # 3단계: 둘 다 데이터가 없을 시 임시 기준
    if not is_fitted:
        dummy_X = np.array([[0.0], [1.0]])
        dummy_y = np.array([0.0, 0.1]) 
        calibrator.fit(dummy_X, dummy_y)

    print(f"[5/6] {latest_date.date()} 기준 실전 추론 및 SHAP 요인 분석...")
    snapshot_mask = df_m["trade_date"] == latest_date
    df_inf = df_m.loc[snapshot_mask].copy()
    X_inf_imputed = imputer.transform(X_raw.loc[snapshot_mask])
    
    raw_scores = ranker.predict(X_inf_imputed)
    predicted_alpha = calibrator.predict(raw_scores.reshape(-1, 1)) * 100
    df_inf["Expected_Return(%)"] = predicted_alpha

    df_inf = df_inf.merge(df_stock_conf, on="ticker", how="left")
    df_inf["Confidence_Score"] = df_inf["conf_score"].fillna(50.0)
    df_inf["Return_Score"] = df_inf["Expected_Return(%)"].rank(pct=True) * 100
    df_inf["Attractiveness_Score"] = (df_inf["Return_Score"] * 0.5) + (df_inf["Confidence_Score"] * 0.5)
    df_inf = df_inf.replace([np.inf, -np.inf], np.nan)

    explainer = shap.TreeExplainer(ranker)
    updated_feat_cols = imputer.get_feature_names_out(feats)
    shap_values = explainer.shap_values(pd.DataFrame(X_inf_imputed, columns=updated_feat_cols))

    db_insert_data = []
    
    for i, (_, row) in enumerate(df_inf.iterrows()):
        ticker = row['ticker']
        sv = shap_values[i]
        
        agg_shap = {}
        for j, fname in enumerate(updated_feat_cols):
            base_fname = fname.replace("missingindicator_", "")
            if base_fname not in global_exclude_bases:
                agg_shap[base_fname] = agg_shap.get(base_fname, 0) + sv[j]
        
        # 긍정 Top 3 / 부정 Top 3
        pos_feats = sorted([(k, v) for k, v in agg_shap.items() if v > 0], key=lambda x: x[1], reverse=True)[:3]
        neg_feats = sorted([(k, v) for k, v in agg_shap.items() if v < 0], key=lambda x: x[1])[:3]
        
        combined_feats = pos_feats + neg_feats
        top_feat_names = [item[0] for item in combined_feats]
        top_feat_vals = [round(float(item[1]), 4) for item in combined_feats]

        exp_ret = round(float(row['Expected_Return(%)']), 4) if not np.isnan(row['Expected_Return(%)']) else None
        score = round(float(row['Attractiveness_Score']), 4) if not np.isnan(row['Attractiveness_Score']) else None
        conf_val = round(float(row['Confidence_Score']), 4) if not np.isnan(row['Confidence_Score']) else None

        def clean_val(v):
            return float(v) if pd.notnull(v) and not np.isinf(v) else None

        db_insert_data.append((
            latest_date.date(), ticker, exp_ret, score, 
            json.dumps(top_feat_names), json.dumps(top_feat_vals),
            clean_val(metrics['dir_acc']), clean_val(metrics['hit_rate']),
            clean_val(metrics['rank_ic']), clean_val(metrics['ls_spread']), conf_val
        ))

    print(f"[6/6] LONG_PRED_TB 적재 중... (총 {len(db_insert_data)}건)")
    conn = _connect()
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO LONG_PRED_TB (
                pred_date, ticker, expected_ret, score, shap_feature, shap_value, 
                dir_acc, hit_rate, rank_ic, ls_spread, conf_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                expected_ret=VALUES(expected_ret), score=VALUES(score),
                shap_feature=VALUES(shap_feature), shap_value=VALUES(shap_value),
                dir_acc=VALUES(dir_acc), hit_rate=VALUES(hit_rate),
                rank_ic=VALUES(rank_ic), ls_spread=VALUES(ls_spread), conf_score=VALUES(conf_score);
        """
        cur.executemany(sql, db_insert_data)
        conn.commit()
        print("✅ 장기 예측 결과 업데이트 완료")
    except Exception as e:
        print(f"❌ DB 적재 오류: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_long_term_pipeline()