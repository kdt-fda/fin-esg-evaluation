import os
import json
import pandas as pd
import numpy as np
import pymysql
import shap
import scipy.stats as stats
from dotenv import load_dotenv

from xgboost import XGBRanker
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression

import warnings
warnings.filterwarnings('ignore')

from modeling.data_joiner import StockDataJoiner
from modeling.feature_selector import FeatureSelector

load_dotenv()

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
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name
    )

    return conn

def zfill6(x):
    return x.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False).str.strip().str.zfill(6)

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

    for date, group in df_eval.groupby("Date"):
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
    for ticker, group in df_eval.groupby("Ticker"):
        if len(group) < min_obs: continue

        mean_rank_error = group["rank_error"].mean()
        rank_acc_score = (1.0 - mean_rank_error) * 100

        if group["pred_score"].nunique() > 1 and group["excess_ret"].nunique() > 1:
            ic, _ = stats.spearmanr(group["pred_score"], group["excess_ret"])
            ic = 0 if np.isnan(ic) else ic
        else:
            ic = 0

        ts_ic_score = max(0, ic * 100)
        raw_conf_score = (rank_acc_score * 0.6) + (ts_ic_score * 0.4)

        shrink = min(1.0, len(group) / 60.0)
        conf_score = shrink * raw_conf_score + (1.0 - shrink) * 50.0

        confidence_records.append({"Ticker": ticker, "conf_score": conf_score})
    return pd.DataFrame(confidence_records).set_index("Ticker")

# =========================================================================
# 3. 중장기 랭킹 메인 파이프라인
# =========================================================================
def run_long_term_pipeline():
    H_VAL = 189
    print(f"\n[시스템] AI 중장기 랭킹 모델({H_VAL}일 예측) 파이프라인 가동...")

    joiner = StockDataJoiner()
    selector = FeatureSelector()

    # 1. KOSPI 200 종목 가져오기
    conn = _connect()
    try:
        kospi_df = pd.read_sql("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB", conn)
    finally:
        conn.close()

    stock_names = kospi_df['stock_name'].dropna().unique()
    mega_df_list = []
    latest_date = None

    print(f"[1/5] 총 {len(stock_names)}개 종목 데이터 병합 중...")
    
    for s_name in stock_names:
        df = joiner.get_modeling_dataset(s_name)
        if df is None or len(df) < H_VAL + 50:
            continue
            
        df['Ticker'] = zfill6([df['ticker'].iloc[0]])
        df['Date'] = pd.to_datetime(df['trade_date'])
        
        if latest_date is None or df['Date'].max() > latest_date:
            latest_date = df['Date'].max()
            
        mega_df_list.append(df)

    mega_df = pd.concat(mega_df_list, ignore_index=True)
    mega_df = mega_df.sort_values(['Ticker', 'Date']).reset_index(drop=True)

    print(f"[2/5] 횡단면 초과수익률(Target) 및 피처 세팅 중...")
    # 타겟(189일 초과 수익률 및 relevance) 생성
    mega_df['raw_ret'] = mega_df.groupby('Ticker')['close'].shift(-H_VAL) / mega_df['close'] - 1.0
    mega_df['market_median'] = mega_df.groupby('Date')['raw_ret'].transform('median')
    mega_df['excess_ret'] = mega_df['raw_ret'] - mega_df['market_median']

    valid_mask = mega_df['excess_ret'].notna()
    mega_df.loc[valid_mask, 'relevance'] = mega_df[valid_mask].groupby('Date')['excess_ret'].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
    ).fillna(0).astype(int)

    # FeatureSelector로 학습용 피처만 추출
    X_raw = selector.get_features(mega_df, mode='long')
    feat_cols = X_raw.columns.tolist()

    # 엠바고 및 구간 분할
    unique_trading_days = get_trade_calendar(mega_df["Date"])
    valid_idx = int(len(unique_trading_days) * 0.8)
    if valid_idx == 0 or valid_idx >= len(unique_trading_days):
        raise ValueError("[오류] 학습을 위한 데이터가 충분하지 않습니다.")

    valid_start_date = pd.to_datetime(unique_trading_days[valid_idx])
    embargo_limit = get_embargo_limit(unique_trading_days, valid_idx, H_VAL)

    valid_dates = unique_trading_days[valid_idx:]
    split_idx = int(len(valid_dates) * 0.5)
    valid_eval_end_date = pd.to_datetime(valid_dates[split_idx - 1])

    train_mask = mega_df["Date"] <= embargo_limit
    valid_eval_mask = (mega_df["Date"] >= valid_start_date) & (mega_df["Date"] <= valid_eval_end_date)
    valid_calib_mask = mega_df["Date"] > valid_eval_end_date

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    
    # Train
    X_train = imputer.fit_transform(X_raw.loc[train_mask])
    y_train = mega_df.loc[train_mask, "relevance"].values
    qid_train = pd.factorize(mega_df.loc[train_mask, "Date"])[0]

    # Eval
    X_valid_eval = imputer.transform(X_raw.loc[valid_eval_mask])
    y_valid_eval = mega_df.loc[valid_eval_mask, "relevance"].values
    qid_valid_eval = pd.factorize(mega_df.loc[valid_eval_mask, "Date"])[0]

    # Calib
    X_valid_calib = imputer.transform(X_raw.loc[valid_calib_mask])
    excess_ret_valid_calib = mega_df.loc[valid_calib_mask, "excess_ret"].values

    print("[3/5] XGBRanker 학습 시작...")
    ranker = XGBRanker(
        n_estimators=300, max_depth=4, learning_rate=0.03,
        objective="rank:pairwise", subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1
    )
    ranker.fit(
        X_train, y_train, qid=qid_train,
        eval_set=[(X_valid_eval, y_valid_eval)], eval_qid=[qid_valid_eval],
        verbose=False
    )

    print("[4/5] 백테스트 평가 및 실전 기대수익률 보정(Calibrator)...")
    pred_scores_eval = ranker.predict(X_valid_eval)
    df_eval = pd.DataFrame({
        "Date": mega_df.loc[valid_eval_mask, "Date"].values,
        "Ticker": mega_df.loc[valid_eval_mask, "Ticker"].values,
        "pred_score": pred_scores_eval,
        "excess_ret": mega_df.loc[valid_eval_mask, "excess_ret"].values
    })

    # 시장 전체 성능 지표 계산
    market_metrics = evaluate_rank_metrics(df_eval, top_k=20, min_stocks=40)

    # 개별 종목 신뢰도 계산
    df_eval["pred_pct"] = df_eval.groupby("Date")["pred_score"].rank(pct=True)
    df_eval["actual_pct"] = df_eval.groupby("Date")["excess_ret"].rank(pct=True)
    df_eval["rank_error"] = (df_eval["pred_pct"] - df_eval["actual_pct"]).abs()
    df_stock_conf = build_confidence_scores(df_eval, min_obs=20)

    # 기대수익률(Alpha) 캘리브레이션
    pred_scores_calib = ranker.predict(X_valid_calib)
    calibrator = LinearRegression().fit(pred_scores_calib.reshape(-1, 1), excess_ret_valid_calib)

    # 최신 일자 추론 (Inference)
    snapshot_mask = mega_df["Date"] == latest_date
    X_inf_raw = X_raw.loc[snapshot_mask]
    tickers_inf = mega_df.loc[snapshot_mask, "Ticker"].values
    
    X_inf_imputed = imputer.transform(X_inf_raw)
    raw_scores = ranker.predict(X_inf_imputed)
    predicted_alpha = calibrator.predict(raw_scores.reshape(-1, 1)) * 100 # % 단위

    # 매력도 점수 변환 (0~100점)
    return_scores = pd.Series(predicted_alpha).rank(pct=True).values * 100

    print(f"[5/5] {latest_date.date()} 기준 SHAP 추출 및 LONG_PRED_TB 적재 중...")
    explainer = shap.TreeExplainer(ranker)
    shap_values = explainer.shap_values(X_inf_imputed)
    updated_feat_cols = imputer.get_feature_names_out(feat_cols)
    
    # 매크로/공통 변수를 제외하고 순수 기업 지표만 뽑기 위한 필터
    macro_prefixes = ('us_', 'kr_', 'ktb', 'jpy', 'rate_diff', 'mkt_', 'wti', 'brent', 'usdkrw', 'cli')

    db_insert_data = []
    for i, ticker in enumerate(tickers_inf):
        sv = shap_values[i]
        
        valid_pos = {}
        for j, fname in enumerate(updated_feat_cols):
            base_fname = fname.replace("missingindicator_", "")
            # SHAP 값이 양수이고 매크로 변수가 아닌 경우만 필터링
            if sv[j] > 0 and not base_fname.startswith(macro_prefixes):
                valid_pos[base_fname] = valid_pos.get(base_fname, 0) + sv[j]
                
        sorted_features = sorted(valid_pos.items(), key=lambda item: item[1], reverse=True)[:5]
        top_feat_names = [item[0] for item in sorted_features]
        top_feat_vals = [round(float(item[1]), 4) for item in sorted_features]
        
        # 신뢰도 (데이터 부족한 경우 디폴트로 50점 부여)
        conf = df_stock_conf.loc[ticker, "conf_score"] if ticker in df_stock_conf.index else 50.0
        
        # 최종 투자 매력도 산출 (기대수익률 점수 50% + 신뢰도 50%)
        attractiveness_score = (return_scores[i] * 0.5) + (conf * 0.5)

        db_insert_data.append(
            (
                latest_date.date(), ticker,
                round(float(predicted_alpha[i]), 4), # expected_return
                round(float(attractiveness_score), 4), # score
                json.dumps(top_feat_names), json.dumps(top_feat_vals),
                market_metrics['dir_acc'], market_metrics['hit_rate'], 
                market_metrics['rank_ic'], market_metrics['ls_spread'], 
                round(float(conf), 4)
            )
        )

    # DB 최종 적재
    conn = _connect()
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO LONG_PRED_TB (
                pred_date, ticker, expected_return, score, shap_feature, shap_value, 
                dir_acc, hit_rate, rank_ic, ls_spread, conf_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                expected_return=VALUES(expected_return), score=VALUES(score),
                shap_feature=VALUES(shap_feature), shap_value=VALUES(shap_value),
                dir_acc=VALUES(dir_acc), hit_rate=VALUES(hit_rate),
                rank_ic=VALUES(rank_ic), ls_spread=VALUES(ls_spread),
                conf_score=VALUES(conf_score);
        """
        cur.executemany(sql, db_insert_data)
        conn.commit()
        print(f"✅ LONG_PRED_TB 업데이트 완벽 성공! (총 {len(db_insert_data)}건)")
    except Exception as e:
        print(f"❌ DB 적재 오류: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_long_term_pipeline()