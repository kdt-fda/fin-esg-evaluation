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


# ---------------------------------------------------------
# 0. Utils
# ---------------------------------------------------------
def zfill6(x: pd.Series) -> pd.Series:
    return (
        x.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace("-", "", regex=False)
        .str.strip()
        .str.zfill(6)
    )


def get_trade_calendar(dates: pd.Series) -> np.ndarray:
    cal = pd.to_datetime(dates, errors="coerce").dropna().unique()
    return np.sort(cal.astype("datetime64[ns]"))


def get_embargo_limit(unique_trading_days: np.ndarray, valid_start_idx: int, horizon_h: int) -> pd.Timestamp:
    # off-by-one 방지
    embargo_pos = valid_start_idx - horizon_h - 1
    if embargo_pos < 0:
        raise ValueError("[시스템 오류] 엠바고를 적용할 만큼 충분한 학습 이력이 없습니다.")
    return pd.to_datetime(unique_trading_days[embargo_pos])


def safe_mean(values, default=0.0):
    return float(np.mean(values)) if len(values) > 0 else default


def safe_merge_asof(left, right, on=None, left_on=None, right_on=None, by=None, **kwargs):
    left = left.copy()
    right = right.copy()

    if left_on and right_on:
        left[left_on] = pd.to_datetime(left[left_on], errors="coerce").astype("datetime64[ns]")
        right[right_on] = pd.to_datetime(right[right_on], errors="coerce").astype("datetime64[ns]")
        key_left = left_on
        key_right = right_on
    elif on:
        left[on] = pd.to_datetime(left[on], errors="coerce").astype("datetime64[ns]")
        right[on] = pd.to_datetime(right[on], errors="coerce").astype("datetime64[ns]")
        key_left = on
        key_right = on
    else:
        raise ValueError("safe_merge_asof requires 'on' or both 'left_on' and 'right_on'.")

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

        merged = pd.merge_asof(
            lgrp,
            rgrp,
            on=on,
            left_on=left_on,
            right_on=right_on,
            **kwargs
        )
        out.append(merged)

    if not out:
        return left.iloc[0:0].copy()

    merged_df = pd.concat(out, axis=0, ignore_index=True)

    if by not in merged_df.columns:
        if f"{by}_x" in merged_df.columns:
            merged_df[by] = merged_df[f"{by}_x"]
        elif f"{by}_y" in merged_df.columns:
            merged_df[by] = merged_df[f"{by}_y"]

    merged_df = merged_df.drop(
        columns=[c for c in [f"{by}_x", f"{by}_y"] if c in merged_df.columns],
        errors="ignore"
    )
    return merged_df


# ---------------------------------------------------------
# 1. 메가 데이터 로더
# ---------------------------------------------------------
def load_mega_data_from_db():
    print("[시스템] DB 추출: 서버에서 메가 데이터 결합 중...")

    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")

    if not all([db_host, db_port, db_user, db_password, db_name]):
        raise ValueError(
            "[시스템 오류] DB 환경변수가 완전히 설정되지 않았습니다. "
            "(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME 확인 필요)"
        )

    engine = create_engine(f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

    stocks = pd.read_sql("SELECT * FROM STOCK_TB", engine).rename(
        columns={"trade_date": "Date", "ticker": "Ticker", "close": "Close"}
    )
    stocks["Date"] = pd.to_datetime(stocks["Date"], errors="coerce").astype("datetime64[ns]")
    stocks["Ticker"] = zfill6(stocks["Ticker"])
    stocks = (
        stocks.dropna(subset=["Date", "Ticker", "Close"])
        .sort_values(["Ticker", "Date"])
        .reset_index(drop=True)
    )

    macro = pd.read_sql("SELECT * FROM MACROECONOMICS_TB", engine).rename(columns={"trade_date": "Date"})
    macro["Date"] = pd.to_datetime(macro["Date"], errors="coerce").astype("datetime64[ns]")

    common = pd.read_sql("SELECT * FROM COMMON_TB", engine).rename(columns={"trade_date": "Date"})
    common["Date"] = pd.to_datetime(common["Date"], errors="coerce").astype("datetime64[ns]")

    fund = pd.read_sql("SELECT * FROM FUNDAMENTAL_TB", engine)
    fund["Ticker"] = zfill6(fund["ticker"])

    def get_actual_release_date(row):
        try:
            y, q = int(row["year"]), int(row["quarter"])
            if q == 1:
                return pd.Timestamp(year=y, month=5, day=15)
            elif q == 2:
                return pd.Timestamp(year=y, month=8, day=15)
            elif q == 3:
                return pd.Timestamp(year=y, month=11, day=14)
            else:
                return pd.Timestamp(year=y + 1, month=3, day=31)
        except Exception:
            return pd.NaT

    fund["Date"] = pd.to_datetime(
        fund.apply(get_actual_release_date, axis=1),
        errors="coerce"
    ).astype("datetime64[ns]")

    fin = (
        fund.dropna(subset=["Date", "Ticker"])
        .sort_values(["Ticker", "Date"])
        .drop_duplicates(subset=["Ticker", "Date"], keep="last")
        .drop(columns=["ticker", "year", "quarter", "Stock_Name", "price", "shares"], errors="ignore")
        .reset_index(drop=True)
    )

    sector_tables = [
        "COMM_TB", "CONSTRUCTION_TB", "CONS_DISC_TB", "CONS_STAPLES_TB",
        "ENER_CHEM_TB", "FINANCE_TB", "HEALTHCARE_TB", "HEAVY_IND_TB",
        "INDUSTRIALS_TB", "IT_TB", "MATERIALS_TB"
    ]

    sector_df = pd.DataFrame()
    for tb in sector_tables:
        try:
            temp = pd.read_sql(f"SELECT * FROM {tb}", engine)
            temp = temp.rename(columns={"trade_date": "Date", "ticker": "Ticker"})

            if "Date" not in temp.columns or "Ticker" not in temp.columns:
                continue

            temp["Date"] = pd.to_datetime(temp["Date"], errors="coerce").astype("datetime64[ns]")
            temp["Ticker"] = zfill6(temp["Ticker"])
            temp = temp.dropna(subset=["Date", "Ticker"])

            sector_df = temp if sector_df.empty else pd.merge(
                sector_df, temp, on=["Date", "Ticker"], how="outer"
            )
        except Exception:
            pass

    kospi_sectors = pd.read_sql(
        "SELECT ticker, stock_name, sector_code FROM KOSPI200_STOCKS_TB",
        engine
    )
    kospi_sectors["ticker"] = zfill6(kospi_sectors["ticker"])

    macro_cols = [c for c in macro.columns if c != "Date"]
    common_cols = [c for c in common.columns if c != "Date"]
    global_exclude_bases = set(macro_cols + common_cols)

    return stocks, macro, common, fin, sector_df, kospi_sectors, global_exclude_bases


# ---------------------------------------------------------
# 2. 피처 엔지니어링
# ---------------------------------------------------------
def engineer_long_term_features(
    stocks,
    macro,
    common,
    fin,
    sector_df,
    kospi_sectors,
    H=189,
    is_inference=False
):
    df = stocks.copy()

    ticker_to_sector = dict(zip(kospi_sectors["ticker"], kospi_sectors["sector_code"]))
    ticker_to_name = dict(zip(kospi_sectors["ticker"], kospi_sectors["stock_name"]))

    df["Sector_Name"] = df["Ticker"].map(ticker_to_sector).fillna("Unknown")
    df["Stock_Name"] = df["Ticker"].map(ticker_to_name).fillna("Unknown")

    unique_sectors = sorted(list(set(ticker_to_sector.values())))
    sector_to_id = {name: i for i, name in enumerate(unique_sectors)}
    df["Sector"] = df["Ticker"].map(ticker_to_sector).map(sector_to_id).fillna(-1).astype(int)

    # 모멘텀
    df["mom_1m"] = df.groupby("Ticker")["Close"].pct_change(20)
    df["mom_1_6"] = df.groupby("Ticker")["Close"].shift(20) / df.groupby("Ticker")["Close"].shift(120) - 1
    df["mom_7_12"] = df.groupby("Ticker")["Close"].shift(120) / df.groupby("Ticker")["Close"].shift(250) - 1
    df["rank_mom_7_12"] = df.groupby("Date")["mom_7_12"].rank(pct=True)
    df["rank_mom_1_6"] = df.groupby("Date")["mom_1_6"].rank(pct=True)

    if "foreign_net_amt" in df.columns and "volume" in df.columns:
        df["foreign_dominance"] = df["foreign_net_amt"] / ((df["volume"] * df["Close"]) + 1)
    else:
        df["foreign_dominance"] = np.nan

    # inference에서는 미래 타깃 계산 금지
    if not is_inference:
        df["raw_ret"] = df.groupby("Ticker")["Close"].shift(-H) / df["Close"] - 1
        df["market_median"] = df.groupby("Date")["raw_ret"].transform("median")
        df["excess_ret"] = df["raw_ret"] - df["market_median"]

        df = df.dropna(subset=["excess_ret"]).copy()
        df["relevance"] = df.groupby("Date")["excess_ret"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
        )
        df["relevance"] = df["relevance"].fillna(0).astype(int)
    else:
        df["raw_ret"] = np.nan
        df["market_median"] = np.nan
        df["excess_ret"] = np.nan
        df["relevance"] = 0

    # 재무 병합
    if not fin.empty:
        df = safe_merge_asof(
            df.sort_values(["Ticker", "Date"]).reset_index(drop=True),
            fin.sort_values(["Ticker", "Date"]).reset_index(drop=True),
            on="Date",
            by="Ticker",
            direction="backward"
        )

    # 거시/공통 병합
    df = df.merge(macro, on="Date", how="left").merge(common, on="Date", how="left")

    # 섹터 세부 테이블 병합
    if not sector_df.empty and "Date" in sector_df.columns and "Ticker" in sector_df.columns:
        s = sector_df.copy()
        s["Date"] = pd.to_datetime(s["Date"], errors="coerce").astype("datetime64[ns]")
        s["Ticker"] = zfill6(s["Ticker"])
        df = df.merge(s, on=["Date", "Ticker"], how="left")

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.sort_values(["Date", "Ticker"]).reset_index(drop=True)

    ignore = {
        "Close", "raw_ret", "market_median", "excess_ret", "relevance",
        "Date", "Ticker", "Stock_Name", "Sector_Name"
    }
    feats = [c for c in df.columns if c not in ignore and pd.api.types.is_numeric_dtype(df[c])]
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

    for date, group in df_eval.groupby("Date"):
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

    for ticker, group in df_eval.groupby("Ticker"):
        if len(group) < min_obs:
            continue

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

        confidence_records.append({
            "Ticker": ticker,
            "Confidence_Score": conf_score
        })

    return pd.DataFrame(confidence_records)


# ---------------------------------------------------------
# 4. 메인 파이프라인
# ---------------------------------------------------------
def run_long_term_pipeline():
    H_VAL = 189
    print(f"\n[시스템] 9개월({H_VAL}일) 예측 모델 파이프라인 가동...")

    stocks, macro, common, fin, sector_df, kospi_sectors, global_exclude_bases = load_mega_data_from_db()
    latest_date = pd.to_datetime(stocks["Date"].max())

    imputer = SimpleImputer(strategy="median", add_indicator=True)

    df_m, X_raw, feat_cols = engineer_long_term_features(
        stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=False
    )

    unique_trading_days = get_trade_calendar(df_m["Date"])
    valid_idx = int(len(unique_trading_days) * 0.8)

    if valid_idx == 0 or valid_idx >= len(unique_trading_days):
        raise ValueError("[시스템 오류] 학습을 위한 데이터가 충분하지 않습니다.")

    valid_start_date = pd.to_datetime(unique_trading_days[valid_idx])
    embargo_limit = get_embargo_limit(unique_trading_days, valid_idx, H_VAL)

    valid_dates = unique_trading_days[valid_idx:]
    split_idx = int(len(valid_dates) * 0.5)
    if split_idx <= 0 or split_idx >= len(valid_dates):
        raise ValueError("[시스템 오류] 검증/보정 분할을 위한 데이터가 충분하지 않습니다.")

    valid_eval_end_date = pd.to_datetime(valid_dates[split_idx - 1])

    train_mask = df_m["Date"] <= embargo_limit
    valid_eval_mask = (df_m["Date"] >= valid_start_date) & (df_m["Date"] <= valid_eval_end_date)
    valid_calib_mask = df_m["Date"] > valid_eval_end_date

    print(f"[시스템] Train 종료일(엠바고 적용): {embargo_limit.date()}")
    print(f"[시스템] Eval 구간: {valid_start_date.date()} ~ {valid_eval_end_date.date()}")
    print(f"[시스템] Calib 구간: {pd.to_datetime(valid_dates[split_idx]).date()} ~ {pd.to_datetime(valid_dates[-1]).date()}")

    # train
    X_train = imputer.fit_transform(X_raw.loc[train_mask])
    y_train_relevance = df_m.loc[train_mask, "relevance"].values
    qid_train = pd.factorize(pd.to_datetime(df_m.loc[train_mask, "Date"]))[0]

    # eval
    X_valid_eval = imputer.transform(X_raw.loc[valid_eval_mask])
    y_valid_eval_relevance = df_m.loc[valid_eval_mask, "relevance"].values
    qid_valid_eval = pd.factorize(pd.to_datetime(df_m.loc[valid_eval_mask, "Date"]))[0]

    dates_valid_eval = df_m.loc[valid_eval_mask, "Date"].values
    tickers_valid_eval = df_m.loc[valid_eval_mask, "Ticker"].values
    excess_ret_valid_eval = df_m.loc[valid_eval_mask, "excess_ret"].values

    # calib
    X_valid_calib = imputer.transform(X_raw.loc[valid_calib_mask])
    excess_ret_valid_calib = df_m.loc[valid_calib_mask, "excess_ret"].values

    print("[시스템] XGBRanker 학습 시작...")
    ranker = XGBRanker(
        n_estimators=300,
        learning_rate=0.03,
        max_depth=4,
        objective="rank:pairwise",
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )
    ranker.fit(
        X_train,
        y_train_relevance,
        qid=qid_train,
        eval_set=[(X_valid_eval, y_valid_eval_relevance)],
        eval_qid=[qid_valid_eval],
        verbose=False
    )

    # ---------------------------------------------------------
    # 5. 평가
    # ---------------------------------------------------------
    pred_scores_eval = ranker.predict(X_valid_eval)
    df_eval = pd.DataFrame({
        "Date": dates_valid_eval,
        "Ticker": tickers_valid_eval,
        "pred_score": pred_scores_eval,
        "excess_ret": excess_ret_valid_eval
    })

    metric_result = evaluate_rank_metrics(df_eval, top_k=20, min_stocks=40)

    print("\n" + "=" * 50)
    print("[평가] 9개월 모델 전체 성능 지표")
    print("-" * 50)
    print(f"방향성 적중률       : {metric_result['directional_accuracy_pct']:.2f}%")
    print(f"실전 Top 20 적중률  : {metric_result['topk_hit_rate_pct']:.2f}%")
    print(f"평균 Rank IC        : {metric_result['rank_ic_mean']:.4f}")
    print(f"Top20-Btm20 Spread  : {metric_result['long_short_spread_pctp']:.2f}%p")
    print(f"IC 유효 평가일수    : {metric_result['valid_ic_days']}")
    print("=" * 50)

    # ---------------------------------------------------------
    # 6. 기업별 신뢰도 및 기대수익률
    # ---------------------------------------------------------
    df_eval["pred_pct"] = df_eval.groupby("Date")["pred_score"].rank(pct=True)
    df_eval["actual_pct"] = df_eval.groupby("Date")["excess_ret"].rank(pct=True)
    df_eval["rank_error"] = (df_eval["pred_pct"] - df_eval["actual_pct"]).abs()

    df_stock_conf = build_confidence_scores(df_eval, min_obs=20)

    pred_scores_calib = ranker.predict(X_valid_calib)
    calibrator = LinearRegression().fit(pred_scores_calib.reshape(-1, 1), excess_ret_valid_calib)

    df_inf, X_inf, _ = engineer_long_term_features(
        stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=True
    )
    snapshot_mask = df_inf["Date"] == latest_date

    X_inf_imputed = imputer.transform(X_inf.loc[snapshot_mask])
    raw_scores = ranker.predict(X_inf_imputed)
    predicted_alpha = calibrator.predict(raw_scores.reshape(-1, 1)) * 100

    res_all = df_inf.loc[snapshot_mask, ["Ticker", "Stock_Name", "Sector_Name"]].copy()
    res_all["Expected_Return(%)"] = predicted_alpha
    res_all = pd.merge(res_all, df_stock_conf, on="Ticker", how="left")
    res_all["Confidence_Score"] = res_all["Confidence_Score"].fillna(50.0)

    res_all["Return_Score"] = res_all["Expected_Return(%)"].rank(pct=True) * 100
    res_all["Attractiveness_Score"] = (res_all["Return_Score"] * 0.5) + (res_all["Confidence_Score"] * 0.5)

    # ---------------------------------------------------------
    # 7. SHAP 요인 분석
    # ---------------------------------------------------------
    print("[시스템] SHAP 요인 분석 및 대시보드 생성 중...")
    explainer = shap.TreeExplainer(ranker)
    updated_feat_cols = imputer.get_feature_names_out(feat_cols)
    shap_values = explainer.shap_values(pd.DataFrame(X_inf_imputed, columns=updated_feat_cols))

    ranking_drivers = []
    for i in range(len(res_all)):
        sv = shap_values[i]
        valid_pos_idx = []

        for j, fname in enumerate(updated_feat_cols):
            base_fname = fname.replace("missingindicator_", "")
            if base_fname not in global_exclude_bases and sv[j] > 0:
                valid_pos_idx.append(j)

        if valid_pos_idx:
            sorted_idx = sorted(valid_pos_idx, key=lambda x: sv[x], reverse=True)[:5]
            reasons = [
                f"{updated_feat_cols[j].replace('missingindicator_', '')} (+{sv[j]:.3f})"
                for j in sorted_idx
            ]
            ranking_drivers.append(", ".join(reasons))
        else:
            ranking_drivers.append("None")

    res_all["Top_5_Ranking_Drivers"] = ranking_drivers

    res_all = res_all.sort_values(by="Attractiveness_Score", ascending=False).reset_index(drop=True)
    res_all["Attractiveness_Score"] = res_all["Attractiveness_Score"].round(1)
    res_all["Expected_Return(%)"] = res_all["Expected_Return(%)"].round(2)
    res_all["Confidence_Score"] = res_all["Confidence_Score"].round(1)

    print("\n" + "=" * 50)
    print(f"[{latest_date.date()} 기준 9개월 섹터별 투자 매력도 TOP 랭킹]")
    print("=" * 50)

    sectors = res_all["Sector_Name"].unique()
    for sector in sectors:
        if sector == "Unknown":
            continue

        sector_print = res_all[res_all["Sector_Name"] == sector].head(3)
        if len(sector_print) == 0:
            continue

        sector_mean = res_all[res_all["Sector_Name"] == sector]["Attractiveness_Score"].mean()
        print(f"\n[ {sector} 섹터 ] 평균 매력도: {sector_mean:.1f}점")
        print("-" * 90)

        for _, row in sector_print.iterrows():
            print(
                f"- {row['Stock_Name']:<10} | 매력도: {row['Attractiveness_Score']}점 "
                f"| 기대수익: {row['Expected_Return(%)']}% | 신뢰도: {row['Confidence_Score']}점"
            )
            print(f"   -> 랭킹 상승 요인: {row['Top_5_Ranking_Drivers']}")


if __name__ == "__main__":
    run_long_term_pipeline()