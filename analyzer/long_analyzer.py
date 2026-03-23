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

def safe_mean(values, default=0.0):
    return float(np.mean(values)) if len(values) > 0 else default

# =========================================================================
# 2. 성능 평가 함수
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

# =========================================================================
# 3. 메인 파이프라인
# =========================================================================
def run_long_term_pipeline():
    H_VAL = 189
    STEP = 63

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

    print("[2/6] Target 생성 중...")
    
    # 타겟 생성
    df_m["raw_ret"] = df_m.groupby("ticker")["close"].shift(-H_VAL) / df_m["close"] - 1.0
    df_m["market_median"] = df_m.groupby("trade_date")["raw_ret"].transform("median")
    df_m["excess_ret"] = df_m["raw_ret"] - df_m["market_median"]

    mask_valid_target = df_m["excess_ret"].notna()

    df_m["relevance"] = np.nan 
    df_m.loc[mask_valid_target, "relevance"] = df_m[mask_valid_target].groupby("trade_date")["excess_ret"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
    )

    df_m = df_m.replace([np.inf, -np.inf], np.nan)

    ignore_cols = {"close", "raw_ret", "market_median", "excess_ret", "relevance", "trade_date", "ticker", "stock_name"}
    feats = [c for c in df_m.columns if c not in ignore_cols and pd.api.types.is_numeric_dtype(df_m[c])]
    X_raw = df_m[feats]

    print("[3/6] 워킹 포워드(Walk-Forward) 검증 중...")
    unique_dates = np.sort(df_m["trade_date"].unique())
    start_idx = int(len(unique_dates) * 0.7)

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    all_metrics, oof_list = [], []
    
    for i in range(start_idx, len(unique_dates), STEP):
        train_end_idx = i - H_VAL 
        if train_end_idx <= 0: continue
        
        train_mask = df_m["trade_date"] <= unique_dates[train_end_idx]
        test_start_date = unique_dates[i]
        test_end_idx = min(i + STEP - 1, len(unique_dates) - 1)
        test_mask = (df_m["trade_date"] >= test_start_date) & (df_m["trade_date"] <= unique_dates[test_end_idx])
        
        if train_mask.sum() == 0 or test_mask.sum() == 0: continue
        
        X_tr = imputer.fit_transform(X_raw.loc[train_mask])
        y_tr = df_m.loc[train_mask, "relevance"].values
        qid_tr = pd.factorize(df_m.loc[train_mask, "trade_date"])[0]
        
        ranker = XGBRanker(n_estimators=150, learning_rate=0.05, max_depth=3, objective="rank:pairwise", n_jobs=-1, random_state=42)
        ranker.fit(X_tr, y_tr, qid=qid_tr)
        
        X_te = imputer.transform(X_raw.loc[test_mask])
        pred_scores = ranker.predict(X_te)
        
        df_step_eval = pd.DataFrame({
            "trade_date": df_m.loc[test_mask, "trade_date"].values, 
            "ticker": df_m.loc[test_mask, "ticker"].values,
            "pred_score": pred_scores, 
            "excess_ret": df_m.loc[test_mask, "excess_ret"].values
        })

        df_step_eval = df_step_eval.dropna(subset=['excess_ret'])
        if len(df_step_eval) == 0:
            continue

        oof_list.append(df_step_eval)
        
        metrics = evaluate_rank_metrics(df_step_eval)
        all_metrics.append(metrics)
        print(f" 구간: {str(test_start_date)[:10]} | Rank IC: {metrics['rank_ic']:.3f} | 방향성 적중률: {metrics['dir_acc']:.1f}%")

    print("[4/6] 전체 재학습 및 Z-Score 캘리브레이션...")
    X_train_final = imputer.fit_transform(X_raw.loc[mask_valid_target]) 
    y_train_final = df_m.loc[mask_valid_target, "relevance"].values
    qid_final = pd.factorize(df_m.loc[mask_valid_target, "trade_date"])[0]
    
    final_ranker = XGBRanker(n_estimators=150, learning_rate=0.05, max_depth=3, objective="rank:pairwise", n_jobs=-1, random_state=42)
    final_ranker.fit(X_train_final, y_train_final, qid=qid_final)
    
    if oof_list:
        df_oof = pd.concat(oof_list)
        df_oof['pred_pct'] = df_oof.groupby('trade_date')['pred_score'].rank(pct=True)
        df_oof['actual_pct'] = df_oof.groupby('trade_date')['excess_ret'].rank(pct=True)
        df_oof['rank_error'] = (df_oof['pred_pct'] - df_oof['actual_pct']).abs()
        ticker_rel = (1 - df_oof.groupby('ticker')['rank_error'].mean()) * 100
        
        df_oof['score_z'] = df_oof.groupby('trade_date')['pred_score'].transform(lambda x: (x - x.mean()) / (x.std() + 1e-8))
        df_oof_calib = df_oof.dropna(subset=['score_z', 'excess_ret'])
        
        if len(df_oof_calib) > 10:
            calibrator = LinearRegression().fit(df_oof_calib[["score_z"]], df_oof_calib["excess_ret"])
        else:
            oof_list = []
    
    if not oof_list:
        ticker_rel = pd.Series(dtype=float)
        raw_train_scores = final_ranker.predict(X_train_final)
        train_scores_z = (raw_train_scores - raw_train_scores.mean()) / (raw_train_scores.std() + 1e-8)
        calibrator = LinearRegression().fit(train_scores_z.reshape(-1, 1), df_m.loc[mask_valid_target, "excess_ret"].values)

    print(f"[5/6] {latest_date.date()} 기준 실전 추론 및 SHAP 요인 분석...")
    snapshot_mask = df_m["trade_date"] == latest_date
    df_inf = df_m.loc[snapshot_mask].copy()
    X_inf_snap = X_raw.loc[snapshot_mask].copy()
    
    X_inf_final = imputer.transform(X_inf_snap)
    raw_scores = final_ranker.predict(X_inf_final)
    
    raw_scores_z = (raw_scores - raw_scores.mean()) / (raw_scores.std() + 1e-8)
    exp_ret = calibrator.predict(raw_scores_z.reshape(-1, 1)) * 100
    
    df_inf["Expected_Return(%)"] = exp_ret
    
    score_dev = np.abs(raw_scores - np.median(raw_scores))
    sig_strength = pd.Series(score_dev).rank(pct=True).values * 100
    
    df_inf = df_inf.merge(ticker_rel.rename('hist_rel'), on='ticker', how='left')
    default_rel = df_inf['hist_rel'].median() if not df_inf['hist_rel'].isna().all() else 50.0
    df_inf['hist_rel'] = df_inf['hist_rel'].fillna(default_rel)
    
    df_inf["Confidence_Score"] = (sig_strength * 0.4) + (df_inf['hist_rel'] * 0.6)
    df_inf["Return_Score"] = df_inf["Expected_Return(%)"].rank(pct=True) * 100
    df_inf["Attractiveness_Score"] = (df_inf["Return_Score"] * 0.5 + df_inf["Confidence_Score"] * 0.5)

    explainer = shap.TreeExplainer(final_ranker)
    shap_values = explainer.shap_values(X_inf_final)
    feature_names = imputer.get_feature_names_out(feats)
    
    db_insert_data = []
    
    avg_dir_acc = np.mean([m['dir_acc'] for m in all_metrics]) if all_metrics else 50.0
    avg_hit_rate = np.mean([m['hit_rate'] for m in all_metrics]) if all_metrics else 50.0
    avg_rank_ic = np.mean([m['rank_ic'] for m in all_metrics]) if all_metrics else 0.0
    avg_ls_spread = np.mean([m['ls_spread'] for m in all_metrics]) if all_metrics else 0.0

    def clean_val(v):
        return float(v) if pd.notnull(v) and not np.isinf(v) else None

    for i, (_, row) in enumerate(df_inf.iterrows()):
        ticker = row['ticker']
        sv = shap_values[i]
        
        agg_shap = {}
        for j, fname in enumerate(feature_names):
            base_fname = fname.replace("missingindicator_", "")
            if base_fname not in global_exclude_bases:
                agg_shap[base_fname] = agg_shap.get(base_fname, 0) + sv[j]
        
        # 긍정 Top 3 / 부정 Top 3
        pos_feats = sorted([(k, v) for k, v in agg_shap.items() if v > 0], key=lambda x: x[1], reverse=True)[:3]
        neg_feats = sorted([(k, v) for k, v in agg_shap.items() if v < 0], key=lambda x: x[1])[:3]
        combined_feats = pos_feats + neg_feats
        
        top_feat_names = [item[0] for item in combined_feats]
        top_feat_vals = [round(float(item[1]), 4) for item in combined_feats]

        db_insert_data.append((
            latest_date.date(), ticker, 
            clean_val(row['Expected_Return(%)']), clean_val(row['Attractiveness_Score']), 
            json.dumps(top_feat_names), json.dumps(top_feat_vals),
            clean_val(avg_dir_acc), clean_val(avg_hit_rate),
            clean_val(avg_rank_ic), clean_val(avg_ls_spread), 
            clean_val(row['Confidence_Score'])
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