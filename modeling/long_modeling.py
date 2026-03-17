import os
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
import pymysql
import scipy.stats as stats
import shap

from xgboost import XGBRanker
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression

import warnings
warnings.filterwarnings("ignore")

# =========================================================================
# DB 관리자 제공: 피처 선택 클래스
# =========================================================================
class FeatureSelector:
    def __init__(self):
        self.common_base = [
            'trade_date', 'ticker', 'stock_name', 'open', 'high', 'low', 'close', 
            'volume', 'short_balance', 'news_score', 'usdkrw', 'wti', 'brent', 
            'close_kospi200', 'bull_dummy', 'mkt_ret', 'mkt_vol_20', 'vol_threshold', 
            'high_vol_dummy', 'mkt_regime', 'cli', 'cli_lag1', 'cli_lag3', 'cli_lag6'
        ]

        self.short_term_list = [
            'ma5', 'ma20', 'foreign_net_amt', 'inst_net_amt', 'rsi', 'macd', 
            'macd_signal', 'bb_upper', 'bb_lower', 'bb_breakout', 
            'golden_cross_5_20', 'death_cross_5_20', 'msci_event'
        ]

        self.long_term_list = [
            'ma60', 'ma120', 'ma200', 'golden_cross_20_60', 'death_cross_20_60',
            'revenue', 'revenue_growth', 'operating_income', 'operating_margin', 
            'net_income', 'depreciation', 'rnd_expense', 'roe', 'roa', 'debt_ratio', 
            'shares', 'market_cap', 'per', 'pbr', 'ebitda', 'ev_ebitda',
            'us_cpi', 'us_core_cpi', 'us_core_pce', 'us_unrate', 'us_init_claims',
            'us_policy_rate', 'base_rate', 'us_ust_3y', 'us_ust_10y', 'ktb3y', 'ktb10y', 
            'kr_cpi', 'unemployment_rate', 'ccsi', 'export_total', 'export_yoy', 
            'import_total', 'import_yoy', 'gdp_level', 'gdp_qoq', 'jpy3', 'jpy10', 
            'pmi', 'rate_diff_policy', 'rate_diff_3y', 'rate_diff_10y'
        ]

    def _get_sector_derivative_features(self, df):
        try:
            cols = list(df.columns)
            start_idx = cols.index('cli_lag6') + 1
            end_idx = cols.index('revenue')
            
            if start_idx < end_idx:
                return cols[start_idx:end_idx]
            return []
        except (ValueError, IndexError):
            return []

    def get_features(self, df, mode='long'):
        sector_features = self._get_sector_derivative_features(df)
        common_total = self.common_base + sector_features
        
        if mode == 'short':
            selected_features = common_total + self.short_term_list
        elif mode == 'long':
            selected_features = common_total + self.long_term_list
        else:
            selected_features = list(set(common_total + self.short_term_list + self.long_term_list))

        final_cols = [c for c in selected_features if c in df.columns]
        return final_cols

# =========================================================================
# Utils
# =========================================================================
original_merge_asof = pd.merge_asof
def patched_merge_asof(left, right, on=None, left_on=None, right_on=None, **kwargs):
    if left_on and right_on:
        left[left_on] = pd.to_datetime(left[left_on], errors="coerce").astype('datetime64[ns]')
        right[right_on] = pd.to_datetime(right[right_on], errors="coerce").astype('datetime64[ns]')
    elif on:
        left[on] = pd.to_datetime(left[on], errors="coerce").astype('datetime64[ns]')
        right[on] = pd.to_datetime(right[on], errors="coerce").astype('datetime64[ns]')
    return original_merge_asof(left, right, on=on, left_on=left_on, right_on=right_on, **kwargs)
pd.merge_asof = patched_merge_asof

def zfill6(x: pd.Series) -> pd.Series:
    return x.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False).str.strip().str.zfill(6)

def get_trade_calendar(dates: pd.Series) -> np.ndarray:
    cal = pd.to_datetime(dates, errors="coerce").dropna().unique()
    return np.sort(cal.astype("datetime64[ns]"))

def get_embargo_limit(unique_trading_days: np.ndarray, valid_start_idx: int, horizon_h: int) -> pd.Timestamp:
    embargo_pos = valid_start_idx - horizon_h - 1
    if embargo_pos < 0:
        raise ValueError("[시스템 오류] 엠바고를 적용할 만큼 충분한 학습 이력이 없습니다.")
    return pd.to_datetime(unique_trading_days[embargo_pos])

def safe_mean(values, default=0.0):
    return float(np.mean(values)) if len(values) > 0 else default

def safe_merge_asof(left, right, on=None, left_on=None, right_on=None, by=None, **kwargs):
    left = left.copy()
    right = right.copy()

    key_left = left_on if left_on else on
    key_right = right_on if right_on else on

    left[key_left] = pd.to_datetime(left[key_left], errors="coerce").astype("datetime64[ns]")
    right[key_right] = pd.to_datetime(right[key_right], errors="coerce").astype("datetime64[ns]")

    if by is None:
        left = left.dropna(subset=[key_left]).sort_values(key_left).reset_index(drop=True)
        right = right.dropna(subset=[key_right]).sort_values(key_right).reset_index(drop=True)
        return pd.merge_asof(left, right, on=on, left_on=left_on, right_on=right_on, **kwargs)

    left = left.dropna(subset=[by, key_left]).copy()
    right = right.dropna(subset=[by, key_right]).copy()

    out = []
    for gval, lgrp in left.groupby(by, sort=False):
        rgrp = right[right[by] == gval].copy()
        lgrp = lgrp.sort_values(key_left).reset_index(drop=True)

        if rgrp.empty:
            out.append(lgrp)
            continue

        rgrp = rgrp.sort_values(key_right).reset_index(drop=True)
        rgrp = rgrp.drop(columns=[by], errors="ignore")

        merged = pd.merge_asof(lgrp, rgrp, on=on, left_on=left_on, right_on=right_on, **kwargs)
        out.append(merged)

    if not out:
        return left.iloc[0:0].copy()

    merged_df = pd.concat(out, axis=0, ignore_index=True)
    if by not in merged_df.columns:
        if f"{by}_x" in merged_df.columns:
            merged_df[by] = merged_df[f"{by}_x"]
        elif f"{by}_y" in merged_df.columns:
            merged_df[by] = merged_df[f"{by}_y"]

    merged_df = merged_df.drop(columns=[c for c in [f"{by}_x", f"{by}_y"] if c in merged_df.columns], errors="ignore")
    return merged_df

# ---------------------------------------------------------
# 1. 메가 데이터 로더
# ---------------------------------------------------------
def load_mega_data_from_db():
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")

    if not all([db_host, db_port, db_user, db_password, db_name]):
        raise ValueError("[시스템 오류] DB 환경변수가 설정되지 않았습니다.")

    engine = create_engine(f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

    stocks = pd.read_sql("SELECT * FROM STOCK_TB", engine)
    stocks.columns = [c.lower() for c in stocks.columns]
    stocks["trade_date"] = pd.to_datetime(stocks["trade_date"], errors="coerce").astype("datetime64[ns]")
    stocks["ticker"] = zfill6(stocks["ticker"])
    stocks = stocks.dropna(subset=["trade_date", "ticker", "close"]).sort_values(["ticker", "trade_date"]).reset_index(drop=True)

    macro = pd.read_sql("SELECT * FROM MACROECONOMICS_TB", engine)
    macro.columns = [c.lower() for c in macro.columns]
    macro["trade_date"] = pd.to_datetime(macro["trade_date"], errors="coerce").astype("datetime64[ns]")

    common = pd.read_sql("SELECT * FROM COMMON_TB", engine)
    common.columns = [c.lower() for c in common.columns]
    common["trade_date"] = pd.to_datetime(common["trade_date"], errors="coerce").astype("datetime64[ns]")

    fund = pd.read_sql("SELECT * FROM FUNDAMENTAL_TB", engine)
    fund.columns = [c.lower() for c in fund.columns]
    fund["ticker"] = zfill6(fund["ticker"])

    def get_actual_release_date(row):
        try:
            y, q = int(row["year"]), int(row["quarter"])
            if q == 1: return pd.Timestamp(year=y, month=5, day=15)
            elif q == 2: return pd.Timestamp(year=y, month=8, day=15)
            elif q == 3: return pd.Timestamp(year=y, month=11, day=14)
            else: return pd.Timestamp(year=y + 1, month=3, day=31)
        except Exception:
            return pd.NaT

    fund["trade_date"] = pd.to_datetime(fund.apply(get_actual_release_date, axis=1), errors="coerce").astype("datetime64[ns]")
    fin = fund.dropna(subset=["trade_date", "ticker"]).sort_values(["ticker", "trade_date"]).drop_duplicates(subset=["ticker", "trade_date"], keep="last").reset_index(drop=True)

    sector_tables = [
        "COMM_TB", "CONSTRUCTION_TB", "CONS_DISC_TB", "CONS_STAPLES_TB",
        "ENER_CHEM_TB", "FINANCE_TB", "HEALTHCARE_TB", "HEAVY_IND_TB",
        "INDUSTRIALS_TB", "IT_TB", "MATERIALS_TB"
    ]

    sector_df = pd.DataFrame()
    for tb in sector_tables:
        try:
            temp = pd.read_sql(f"SELECT * FROM {tb}", engine)
            temp.columns = [c.lower() for c in temp.columns]
            if "trade_date" not in temp.columns or "ticker" not in temp.columns: continue

            temp["trade_date"] = pd.to_datetime(temp["trade_date"], errors="coerce").astype("datetime64[ns]")
            temp["ticker"] = zfill6(temp["ticker"])
            temp = temp.dropna(subset=["trade_date", "ticker"])
            sector_df = temp if sector_df.empty else pd.merge(sector_df, temp, on=["trade_date", "ticker"], how="outer")
        except Exception:
            pass

    kospi_sectors = pd.read_sql("SELECT ticker, stock_name, sector_code FROM KOSPI200_STOCKS_TB", engine)
    kospi_sectors.columns = [c.lower() for c in kospi_sectors.columns]
    kospi_sectors["ticker"] = zfill6(kospi_sectors["ticker"])

    return stocks, macro, common, fin, sector_df, kospi_sectors

# ---------------------------------------------------------
# 2. 피처 엔지니어링 및 FeatureSelector 적용
# ---------------------------------------------------------
def engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=189, is_inference=False):
    df = stocks.copy()
    selector = FeatureSelector()

    ticker_to_sector = dict(zip(kospi_sectors["ticker"], kospi_sectors["sector_code"]))
    ticker_to_name = dict(zip(kospi_sectors["ticker"], kospi_sectors["stock_name"]))

    df["sector_name"] = df["ticker"].map(ticker_to_sector).fillna("Unknown")
    df["stock_name"] = df["ticker"].map(ticker_to_name).fillna("Unknown")

    if not is_inference:
        df["raw_ret"] = df.groupby("ticker")["close"].shift(-H) / df["close"] - 1
        df["market_median"] = df.groupby("trade_date")["raw_ret"].transform("median")
        df["excess_ret"] = df["raw_ret"] - df["market_median"]
        df = df.dropna(subset=["excess_ret"]).copy()
        df["relevance"] = df.groupby("trade_date")["excess_ret"].transform(lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
        df["relevance"] = df["relevance"].fillna(0).astype(int)
    else:
        df["raw_ret"] = np.nan
        df["market_median"] = np.nan
        df["excess_ret"] = np.nan
        df["relevance"] = 0

    if not fin.empty:
        df = safe_merge_asof(
            df.sort_values(["ticker", "trade_date"]).reset_index(drop=True),
            fin.sort_values(["ticker", "trade_date"]).reset_index(drop=True),
            on="trade_date", by="ticker", direction="backward"
        )

    df = df.merge(macro, on="trade_date", how="left").merge(common, on="trade_date", how="left")

    if not sector_df.empty and "trade_date" in sector_df.columns and "ticker" in sector_df.columns:
        s = sector_df.copy()
        s["trade_date"] = pd.to_datetime(s["trade_date"], errors="coerce").astype("datetime64[ns]")
        s["ticker"] = zfill6(s["ticker"])
        df = df.merge(s, on=["trade_date", "ticker"], how="left")

    df = df.replace([np.inf, -np.inf], np.nan).sort_values(["trade_date", "ticker"]).reset_index(drop=True)

    selected_features = selector.get_features(df, mode='long')
    exclude_targets = {"close", "raw_ret", "market_median", "excess_ret", "relevance", "trade_date", "ticker", "stock_name", "sector_name", "sector_code"}
    
    feats = [c for c in selected_features if c in df.columns and c not in exclude_targets and pd.api.types.is_numeric_dtype(df[c])]
    X = df[feats]

    return df, X, feats

# ---------------------------------------------------------
# 3. 평가 함수
# ---------------------------------------------------------
def evaluate_rank_metrics(df_eval: pd.DataFrame, top_k: int = 20, min_stocks: int = 40):
    daily_ic = []
    long_short_spreads = []
    topk_hit_rates = []
    daily_accuracies = []

    for date, group in df_eval.groupby("trade_date"):
        n_stocks = len(group)
        if n_stocks < min_stocks:
            continue

        ic, _ = stats.spearmanr(group["pred_score"], group["excess_ret"])
        if not np.isnan(ic):
            daily_ic.append(ic)

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
        "directional_accuracy_pct": safe_mean(daily_accuracies) * 100,
        "topk_hit_rate_pct": safe_mean(topk_hit_rates) * 100,
        "rank_ic_mean": safe_mean(daily_ic, default=np.nan),
        "long_short_spread_pctp": safe_mean(long_short_spreads) * 100,
        "valid_ic_days": len(daily_ic),
    }

def build_confidence_scores(df_eval: pd.DataFrame, min_obs: int = 20):
    confidence_records = []
    for ticker, group in df_eval.groupby("ticker"):
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

        confidence_records.append({"ticker": ticker, "Confidence_Score": conf_score})

    return pd.DataFrame(confidence_records)

# ---------------------------------------------------------
# 4. 메인 파이프라인
# ---------------------------------------------------------
def run_long_term_pipeline():
    H_VAL = 189
    stocks, macro, common, fin, sector_df, kospi_sectors = load_mega_data_from_db()
    latest_date = pd.to_datetime(stocks["trade_date"].max())

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    df_m, X_raw, feat_cols = engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=False)

    unique_trading_days = get_trade_calendar(df_m["trade_date"])
    valid_idx = int(len(unique_trading_days) * 0.8)
    if valid_idx == 0 or valid_idx >= len(unique_trading_days):
        raise ValueError("[시스템 오류] 학습 데이터 부족")

    valid_start_date = pd.to_datetime(unique_trading_days[valid_idx])
    embargo_limit = get_embargo_limit(unique_trading_days, valid_idx, H_VAL)

    valid_dates = unique_trading_days[valid_idx:]
    split_idx = int(len(valid_dates) * 0.5)
    valid_eval_end_date = pd.to_datetime(valid_dates[split_idx - 1])

    train_mask = df_m["trade_date"] <= embargo_limit
    valid_eval_mask = (df_m["trade_date"] >= valid_start_date) & (df_m["trade_date"] <= valid_eval_end_date)
    valid_calib_mask = df_m["trade_date"] > valid_eval_end_date

    X_train = imputer.fit_transform(X_raw.loc[train_mask])
    y_train_relevance = df_m.loc[train_mask, "relevance"].values
    qid_train = pd.factorize(pd.to_datetime(df_m.loc[train_mask, "trade_date"]))[0]

    X_valid_eval = imputer.transform(X_raw.loc[valid_eval_mask])
    y_valid_eval_relevance = df_m.loc[valid_eval_mask, "relevance"].values
    qid_valid_eval = pd.factorize(pd.to_datetime(df_m.loc[valid_eval_mask, "trade_date"]))[0]

    X_valid_calib = imputer.transform(X_raw.loc[valid_calib_mask])
    excess_ret_valid_calib = df_m.loc[valid_calib_mask, "excess_ret"].values

    use_gpu = False
    params = {
        "n_estimators": 300, "learning_rate": 0.03, "max_depth": 4,
        "objective": "rank:pairwise", "subsample": 0.8, "colsample_bytree": 0.8,
        "random_state": 42
    }
    try:
        tmp = XGBRanker(tree_method='hist', device='cuda', n_estimators=1)
        tmp.fit(np.array([[0.0]]), np.array([0]), qid=np.array([0]))
        use_gpu = True
        params['tree_method'] = 'hist'
        params['device'] = 'cuda'
    except Exception:
        params['tree_method'] = 'hist'

    params['n_jobs'] = -1

    ranker = XGBRanker(**params)
    ranker.fit(
        X_train, y_train_relevance, qid=qid_train,
        eval_set=[(X_valid_eval, y_valid_eval_relevance)], eval_qid=[qid_valid_eval],
        verbose=False
    )

# ---------------------------------------------------------
# 5. 평가 및 기업별 신뢰도 추출
# ---------------------------------------------------------
    pred_scores_eval = ranker.predict(X_valid_eval)
    df_eval = pd.DataFrame({
        "trade_date": df_m.loc[valid_eval_mask, "trade_date"].values,
        "ticker": df_m.loc[valid_eval_mask, "ticker"].values,
        "pred_score": pred_scores_eval,
        "excess_ret": df_m.loc[valid_eval_mask, "excess_ret"].values
    })

    metric_result = evaluate_rank_metrics(df_eval, top_k=20, min_stocks=40)

    df_eval["pred_pct"] = df_eval.groupby("trade_date")["pred_score"].rank(pct=True)
    df_eval["actual_pct"] = df_eval.groupby("trade_date")["excess_ret"].rank(pct=True)
    df_eval["rank_error"] = (df_eval["pred_pct"] - df_eval["actual_pct"]).abs()
    df_stock_conf = build_confidence_scores(df_eval, min_obs=20)

    pred_scores_calib = ranker.predict(X_valid_calib)
    calibrator = LinearRegression().fit(pred_scores_calib.reshape(-1, 1), excess_ret_valid_calib)

# ---------------------------------------------------------
# 6. 실전 추론 (Inference)
# ---------------------------------------------------------
    df_inf, X_inf, _ = engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=True)
    snapshot_mask = df_inf["trade_date"] == latest_date

    X_inf_imputed = imputer.transform(X_inf.loc[snapshot_mask])
    raw_scores = ranker.predict(X_inf_imputed)
    predicted_alpha = calibrator.predict(raw_scores.reshape(-1, 1)) * 100

    res_all = df_inf.loc[snapshot_mask, ["ticker", "stock_name", "sector_name"]].copy()
    res_all["Expected_Return(%)"] = predicted_alpha
    res_all = pd.merge(res_all, df_stock_conf, on="ticker", how="left")
    res_all["Confidence_Score"] = res_all["Confidence_Score"].fillna(50.0)

    res_all["Return_Score"] = res_all["Expected_Return(%)"].rank(pct=True) * 100
    res_all["Attractiveness_Score"] = (res_all["Return_Score"] * 0.5) + (res_all["Confidence_Score"] * 0.5)

# ---------------------------------------------------------
# 7. SHAP 요인 분석 (긍정 3개, 부정 3개 추출)
# ---------------------------------------------------------
    explainer = shap.TreeExplainer(ranker)
    updated_feat_cols = imputer.get_feature_names_out(feat_cols)
    shap_values = explainer.shap_values(pd.DataFrame(X_inf_imputed, columns=updated_feat_cols))

    exclude_bases = {'trade_date', 'ticker', 'stock_name', 'close', 'sector_name'}

    ranking_drivers = []
    for i in range(len(res_all)):
        sv = shap_values[i]
        pos_idx = []
        neg_idx = []

        for j, fname in enumerate(updated_feat_cols):
            base_fname = fname.replace("missingindicator_", "")
            if base_fname not in exclude_bases:
                if sv[j] > 0:
                    pos_idx.append(j)
                elif sv[j] < 0:
                    neg_idx.append(j)

        top_pos = sorted(pos_idx, key=lambda x: sv[x], reverse=True)[:3]
        top_neg = sorted(neg_idx, key=lambda x: sv[x])[:3]

        reasons = []
        for j in top_pos:
            reasons.append(f"{updated_feat_cols[j].replace('missingindicator_', '')} (+{sv[j]:.3f})")
        for j in top_neg:
            reasons.append(f"{updated_feat_cols[j].replace('missingindicator_', '')} ({sv[j]:.3f})")

        if reasons:
            ranking_drivers.append(", ".join(reasons))
        else:
            ranking_drivers.append("None")

    res_all["Top_Drivers"] = ranking_drivers
    res_all = res_all.sort_values(by="Attractiveness_Score", ascending=False).reset_index(drop=True)
    
    res_all["Attractiveness_Score"] = res_all["Attractiveness_Score"].round(1)
    res_all["Expected_Return(%)"] = res_all["Expected_Return(%)"].round(2)
    res_all["Confidence_Score"] = res_all["Confidence_Score"].round(1)

    return res_all

if __name__ == "__main__":
    df_result = run_long_term_pipeline()