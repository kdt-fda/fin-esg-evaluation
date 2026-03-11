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
warnings.filterwarnings('ignore')

def safe_merge_asof(left, right, on=None, left_on=None, right_on=None, **kwargs):
    if left_on and right_on:
        left[left_on] = pd.to_datetime(left[left_on]).astype('datetime64[ns]')
        right[right_on] = pd.to_datetime(right[right_on]).astype('datetime64[ns]')
    elif on:
        left[on] = pd.to_datetime(left[on]).astype('datetime64[ns]')
        right[on] = pd.to_datetime(right[on]).astype('datetime64[ns]')
    return pd.merge_asof(left, right, on=on, left_on=left_on, right_on=right_on, **kwargs)

# ---------------------------------------------------------
# 1. 메가 데이터 로더
# ---------------------------------------------------------
def load_mega_data_from_db():
    print("🌐 DB 추출: 서버에서 메가 데이터 결합 중...")
    
    db_host = os.environ.get('DB_HOST', '3.34.100.134')
    db_port = os.environ.get('DB_PORT', '3302')
    db_user = os.environ.get('DB_USER', 'root')
    db_password = os.environ.get('DB_PASSWORD', 'team2')
    db_name = os.environ.get('DB_NAME', 'STOCK_DB')
        
    engine = create_engine(f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
    
    def zfill6(x):
        return x.astype(str).str.replace(r"\.0$", "", regex=True).str.replace("-", "", regex=False).str.strip().str.zfill(6)

    stocks = pd.read_sql("SELECT * FROM STOCK_TB", engine).rename(columns={"trade_date": "Date", "ticker": "Ticker", "close": "Close"})
    stocks["Date"] = pd.to_datetime(stocks["Date"]).astype("datetime64[ns]")
    stocks["Ticker"] = zfill6(stocks["Ticker"])
    stocks = stocks.dropna(subset=['Close']).sort_values(["Ticker", "Date"]).reset_index(drop=True)

    macro = pd.read_sql("SELECT * FROM MACROECONOMICS_TB", engine).rename(columns={"trade_date": "Date"})
    macro["Date"] = pd.to_datetime(macro["Date"]).astype("datetime64[ns]")

    common = pd.read_sql("SELECT * FROM COMMON_TB", engine).rename(columns={"trade_date": "Date"})
    common["Date"] = pd.to_datetime(common["Date"]).astype("datetime64[ns]")

    fund = pd.read_sql("SELECT * FROM FUNDAMENTAL_TB", engine)
    fund["Ticker"] = zfill6(fund["ticker"])
    
    def get_actual_release_date(row):
        try:
            y, q = int(row['year']), int(row['quarter'])
            if q == 1: return pd.Timestamp(year=y, month=5, day=15)
            elif q == 2: return pd.Timestamp(year=y, month=8, day=15)
            elif q == 3: return pd.Timestamp(year=y, month=11, day=14)
            else: return pd.Timestamp(year=y+1, month=3, day=31)
        except: return pd.NaT
        
    fund['Date'] = pd.to_datetime(fund.apply(get_actual_release_date, axis=1)).astype("datetime64[ns]")
    fin = fund.dropna(subset=['Date']).sort_values(['Ticker', 'Date'])
    fin = fin.drop(columns=['ticker', 'year', 'quarter', 'Stock_Name', 'price', 'shares'], errors="ignore")

    sector_tables = ['COMM_TB', 'CONSTRUCTION_TB', 'CONS_DISC_TB', 'CONS_STAPLES_TB', 
                     'ENER_CHEM_TB', 'FINANCE_TB', 'HEALTHCARE_TB', 'HEAVY_IND_TB', 
                     'INDUSTRIALS_TB', 'IT_TB', 'MATERIALS_TB']
    
    sector_df = pd.DataFrame()
    for tb in sector_tables:
        try:
            temp = pd.read_sql(f"SELECT * FROM {tb}", engine)
            temp = temp.rename(columns={"trade_date": "Date", "ticker": "Ticker"})
            temp["Date"] = pd.to_datetime(temp["Date"]).astype("datetime64[ns]")
            temp["Ticker"] = zfill6(temp["Ticker"])
            if sector_df.empty:
                sector_df = temp
            else:
                sector_df = pd.merge(sector_df, temp, on=["Date", "Ticker"], how="outer")
        except: pass 

    kospi_sectors = pd.read_sql("SELECT ticker, stock_name, sector_code FROM KOSPI200_STOCKS_TB", engine)
    kospi_sectors["ticker"] = zfill6(kospi_sectors["ticker"])
    
    macro_cols = [c for c in macro.columns if c != 'Date']
    common_cols = [c for c in common.columns if c != 'Date']
    global_exclude_bases = set(macro_cols + common_cols)

    return stocks, macro, common, fin, sector_df, kospi_sectors, global_exclude_bases

# ---------------------------------------------------------
# 2. 피처 엔지니어링
# ---------------------------------------------------------
def engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=189, is_inference=False):
    df = stocks.copy()
    
    ticker_to_sector = dict(zip(kospi_sectors["ticker"], kospi_sectors["sector_code"]))
    ticker_to_name = dict(zip(kospi_sectors["ticker"], kospi_sectors["stock_name"]))
    df['Sector_Name'] = df['Ticker'].map(ticker_to_sector).fillna("Unknown")
    df['Stock_Name'] = df['Ticker'].map(ticker_to_name).fillna("Unknown")
    
    unique_sectors = sorted(list(set(ticker_to_sector.values())))
    sector_to_id = {name: i for i, name in enumerate(unique_sectors)}
    df['Sector'] = df['Ticker'].map(ticker_to_sector).map(sector_to_id).fillna(-1).astype(int)

    df['mom_1m'] = df.groupby('Ticker')['Close'].pct_change(20)
    df['mom_1_6'] = df.groupby('Ticker')['Close'].shift(20) / df.groupby('Ticker')['Close'].shift(120) - 1
    df['mom_7_12'] = df.groupby('Ticker')['Close'].shift(120) / df.groupby('Ticker')['Close'].shift(250) - 1
    df['rank_mom_7_12'] = df.groupby('Date')['mom_7_12'].rank(pct=True)
    df['rank_mom_1_6'] = df.groupby('Date')['mom_1_6'].rank(pct=True)
    
    if 'foreign_net_amt' in df.columns and 'volume' in df.columns:
        df['foreign_dominance'] = df['foreign_net_amt'] / ((df['volume'] * df['Close']) + 1)

    df["raw_ret"] = df.groupby("Ticker")["Close"].shift(-H) / df["Close"] - 1
    df["market_median"] = df.groupby("Date")["raw_ret"].transform("median")
    df["excess_ret"] = df["raw_ret"] - df["market_median"]
    
    if not is_inference:
        df = df.dropna(subset=["excess_ret"])
        df["relevance"] = df.groupby("Date")["excess_ret"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop')
        )
        df["relevance"] = df["relevance"].fillna(0).astype(int)
    else:
        df["relevance"] = 0 
    
    if not fin.empty:
        df = safe_merge_asof(df.sort_values("Date"), fin.sort_values("Date"), on="Date", by="Ticker", direction="backward")
    df = df.merge(macro, on="Date", how="left").merge(common, on="Date", how="left")
    
    if not sector_df.empty:
        df = df.merge(sector_df, on=["Date", "Ticker"], how="left")
        
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.sort_values(["Date", "Ticker"]).reset_index(drop=True)
    
    ignore = {"Close", "raw_ret", "market_median", "excess_ret", "relevance", "Date", "Ticker", "Stock_Name", "Sector_Name"}
    feats = [c for c in df.columns if c not in ignore and pd.api.types.is_numeric_dtype(df[c])]
    X = df[feats]
    
    return df, X, feats

# ---------------------------------------------------------
# 3. 메인 파이프라인
# ---------------------------------------------------------
def run_long_term_pipeline():
    H_VAL = 189
    print(f"\n[시스템] 9개월({H_VAL}일) 예측 모델 파이프라인 가동...")
    stocks, macro, common, fin, sector_df, kospi_sectors, global_exclude_bases = load_mega_data_from_db()
    latest_date = stocks["Date"].max()
    
    imputer = SimpleImputer(strategy="median", add_indicator=True)
    df_m, X_raw, feat_cols = engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=False)

    unique_trading_days = np.sort(df_m['Date'].unique())
    valid_idx = int(len(unique_trading_days) * 0.8)
    
    if valid_idx == 0 or valid_idx >= len(unique_trading_days):
        raise ValueError("데이터가 너무 적습니다.")

    embargo_limit = unique_trading_days[max(0, valid_idx - H_VAL)]
    valid_dates = unique_trading_days[valid_idx:]
    split_idx = int(len(valid_dates) * 0.5)
    valid_eval_end_date = valid_dates[split_idx]
    
    train_mask = df_m["Date"] <= embargo_limit
    valid_eval_mask = (df_m["Date"] >= unique_trading_days[valid_idx]) & (df_m["Date"] <= valid_eval_end_date)
    valid_calib_mask = (df_m["Date"] > valid_eval_end_date)

    X_train = imputer.fit_transform(X_raw.loc[train_mask])
    y_train_relevance = df_m.loc[train_mask, "relevance"].values 
    qid_train = pd.factorize(df_m.loc[train_mask, "Date"])[0]

    X_valid_eval = imputer.transform(X_raw.loc[valid_eval_mask])
    y_valid_eval_relevance = df_m.loc[valid_eval_mask, "relevance"].values
    qid_valid_eval = pd.factorize(df_m.loc[valid_eval_mask, "Date"])[0]
    
    dates_valid_eval = df_m.loc[valid_eval_mask, "Date"].values
    tickers_valid_eval = df_m.loc[valid_eval_mask, "Ticker"].values
    excess_ret_valid_eval = df_m.loc[valid_eval_mask, "excess_ret"].values

    X_valid_calib = imputer.transform(X_raw.loc[valid_calib_mask])
    excess_ret_valid_calib = df_m.loc[valid_calib_mask, "excess_ret"].values

    print("[시스템] XGBRanker 학습 시작...")
    ranker = XGBRanker(
        n_estimators=300, learning_rate=0.03, max_depth=4,
        objective='rank:pairwise', subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1
    )
    ranker.fit(
        X_train, y_train_relevance, qid=qid_train,
        eval_set=[(X_valid_eval, y_valid_eval_relevance)], eval_qid=[qid_valid_eval],
        verbose=False
    )

    # ---------------------------------------------------------
    # 4. 전체 지표 평가
    # ---------------------------------------------------------
    pred_scores_eval = ranker.predict(X_valid_eval)
    df_eval = pd.DataFrame({'Date': dates_valid_eval, 'Ticker': tickers_valid_eval, 'pred_score': pred_scores_eval, 'excess_ret': excess_ret_valid_eval})
    
    daily_accuracies = []
    top20_hit_rates = []

    for date, group in df_eval.groupby('Date'):
        n_stocks = len(group)
        if n_stocks < 40: continue 
        
        group_sorted = group.sort_values('pred_score', ascending=False)
        hit_rate = (group_sorted.head(20)['excess_ret'] > 0).mean()
        top20_hit_rates.append(hit_rate)

        group['pred_rank'] = group['pred_score'].rank(ascending=False)
        group['pred_direction'] = (group['pred_rank'] <= (n_stocks / 2)).astype(int)
        group['actual_direction'] = (group['excess_ret'] > 0).astype(int)
        acc = (group['pred_direction'] == group['actual_direction']).mean()
        daily_accuracies.append(acc)

    overall_dir_acc = np.mean(daily_accuracies) * 100 if daily_accuracies else 0
    overall_top20_hit = np.mean(top20_hit_rates) * 100 if top20_hit_rates else 0

    daily_ic = []
    for d, grp in df_eval.groupby('Date'):
        if len(grp) > 1:
            ic, _ = stats.spearmanr(grp['pred_score'], grp['excess_ret'])
            if not np.isnan(ic): daily_ic.append(ic)
    overall_rank_ic = np.mean(daily_ic)

    print("\n" + "=" * 50)
    print(f" [9개월 모델] 전체 방향성 적중률 : {overall_dir_acc:.2f}%")
    print(f" [9개월 모델] 실전 Top 20 적중률: {overall_top20_hit:.2f}%")
    print(f" [9개월 모델] 평균 Rank IC      : {overall_rank_ic:.4f}")
    print("=" * 50)

    # ---------------------------------------------------------
    # 5. 기업별 신뢰도 및 기대수익률 
    # ---------------------------------------------------------
    df_eval['pred_pct'] = df_eval.groupby('Date')['pred_score'].rank(pct=True)
    df_eval['actual_pct'] = df_eval.groupby('Date')['excess_ret'].rank(pct=True)
    df_eval['rank_error'] = abs(df_eval['pred_pct'] - df_eval['actual_pct'])
    
    confidence_records = []
    for ticker, group in df_eval.groupby('Ticker'):
        if len(group) < 20: continue
        mean_rank_error = group['rank_error'].mean()
        rank_acc_score = (1.0 - mean_rank_error) * 100
        
        if group['pred_score'].nunique() > 1 and group['excess_ret'].nunique() > 1:
            ic, _ = stats.spearmanr(group['pred_score'], group['excess_ret'])
            if np.isnan(ic): ic = 0
        else: ic = 0
            
        ts_ic_score = max(0, ic * 100)
        conf_score = (rank_acc_score * 0.6) + (ts_ic_score * 0.4)
        confidence_records.append({'Ticker': ticker, 'Confidence_Score': conf_score})

    df_stock_conf = pd.DataFrame(confidence_records)

    pred_scores_calib = ranker.predict(X_valid_calib)
    calibrator = LinearRegression().fit(pred_scores_calib.reshape(-1, 1), excess_ret_valid_calib)

    df_inf, X_inf, _ = engineer_long_term_features(stocks, macro, common, fin, sector_df, kospi_sectors, H=H_VAL, is_inference=True)
    snapshot_mask = df_inf["Date"] == latest_date

    X_inf_imputed = imputer.transform(X_inf.loc[snapshot_mask])
    raw_scores = ranker.predict(X_inf_imputed)
    predicted_alpha = calibrator.predict(raw_scores.reshape(-1, 1)) * 100

    res_all = df_inf.loc[snapshot_mask, ["Ticker", "Stock_Name", "Sector_Name"]].copy()
    res_all["Expected_Return(%)"] = predicted_alpha
    res_all = pd.merge(res_all, df_stock_conf, on='Ticker', how='left')
    res_all['Confidence_Score'] = res_all['Confidence_Score'].fillna(50.0)

    # 투자 매력도 산출
    res_all['Return_Score'] = res_all['Expected_Return(%)'].rank(pct=True) * 100
    res_all['Attractiveness_Score'] = (res_all['Return_Score'] * 0.5) + (res_all['Confidence_Score'] * 0.5)

    # ---------------------------------------------------------
    # 6. SHAP 요인 분석 및 대시보드 출력
    # ---------------------------------------------------------
    print("[시스템] SHAP 요인 분석 및 대시보드 생성 중...")
    explainer = shap.TreeExplainer(ranker)
    updated_feat_cols = imputer.get_feature_names_out(feat_cols)
    shap_values = explainer.shap_values(pd.DataFrame(X_inf_imputed, columns=updated_feat_cols))
    
    positive_reasons = []
    for i in range(len(res_all)):
        sv = shap_values[i]
        valid_idx = []
        for j, fname in enumerate(updated_feat_cols):
            base_fname = fname.replace('missingindicator_', '')
            if base_fname not in global_exclude_bases and sv[j] > 0:
                valid_idx.append(j)
        
        if valid_idx:
            sorted_idx = sorted(valid_idx, key=lambda x: sv[x], reverse=True)[:5]
            reasons = [f"{updated_feat_cols[j].replace('missingindicator_', '')} (+{sv[j]:.3f})" for j in sorted_idx]
            positive_reasons.append(", ".join(reasons))
        else:
            positive_reasons.append("None")
            
    res_all['Top_5_Positive_Factors'] = positive_reasons
    
    res_all = res_all.sort_values(by='Attractiveness_Score', ascending=False).reset_index(drop=True)
    res_all['Attractiveness_Score'] = res_all['Attractiveness_Score'].round(1)
    res_all['Expected_Return(%)'] = res_all['Expected_Return(%)'].round(2)
    res_all['Confidence_Score'] = res_all['Confidence_Score'].round(1)

    print(f"  {latest_date.date()} 기준 [9개월 섹터별 투자 매력도 TOP 랭킹]")

    sectors = res_all['Sector_Name'].unique()
    for sector in sectors:
        if sector == "Unknown": continue
        sector_df_print = res_all[res_all['Sector_Name'] == sector].head(3)
        if len(sector_df_print) == 0: continue
            
        print(f"\n📁 [ {sector} 섹터 ] 평균 매력도: {res_all[res_all['Sector_Name'] == sector]['Attractiveness_Score'].mean():.1f}점")
        print("-" * 90)
        
        for _, row in sector_df_print.iterrows():
            print(f"🔹 {row['Stock_Name']:<10} | 매력도: {row['Attractiveness_Score']}점 | 기대수익: {row['Expected_Return(%)']}% | 신뢰도: {row['Confidence_Score']}점")
            print(f"   ↳ 긍정 요인: {row['Top_5_Positive_Factors']}")
    
if __name__ == "__main__":
    run_long_term_pipeline()