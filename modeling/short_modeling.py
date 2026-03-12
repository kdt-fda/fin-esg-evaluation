import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import pymysql
import shap

from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error

import warnings
warnings.filterwarnings('ignore')

# =========================================================================
# 판다스 날짜 에러 우회 패치
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

# ---------------------------------------------------------
# 1. DB 로더 및 공통 변수 식별
# ---------------------------------------------------------
def load_mega_data_from_db():
    # 환경변수 호출 
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    
    # 환경변수 누락 시 에러 발생
    if not all([db_host, db_port, db_user, db_password, db_name]):
        raise ValueError("[시스템 오류] DB 연결을 위한 환경변수가 설정되지 않았습니다. 실행 전 환경변수를 셋팅해주세요.")
    
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

    try:
        news = pd.read_sql("SELECT * FROM NEWS_TB", engine)
        if 'trade_date' in news.columns: news = news.rename(columns={"trade_date": "Date"})
        if 'ticker' in news.columns: 
            news = news.rename(columns={"ticker": "Ticker"})
            news["Ticker"] = zfill6(news["Ticker"])
        news["Date"] = pd.to_datetime(news["Date"]).astype("datetime64[ns]")
    except:
        news = pd.DataFrame()

    kospi_sectors = pd.read_sql("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB", engine)
    
    macro_cols = [c for c in macro.columns if c != 'Date']
    common_cols = [c for c in common.columns if c != 'Date']
    global_exclude_bases = set(macro_cols + common_cols + ['msci_rebal_month'])
    
    return engine, stocks, macro, common, news, kospi_sectors, global_exclude_bases

# ---------------------------------------------------------
# 2. 기술적 지표 생성
# ---------------------------------------------------------
def apply_technical_indicators(df):
    df = df.sort_values('Date').copy()
    
    df['ma_5'] = df['Close'].rolling(window=5).mean()
    df['ma_20'] = df['Close'].rolling(window=20).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    std_20 = df['Close'].rolling(window=20).std()
    df['bb_upper'] = df['ma_20'] + (std_20 * 2)
    df['bb_lower'] = df['ma_20'] - (std_20 * 2)
    df['bb_breakout'] = np.where(df['Close'] > df['bb_upper'], 1, np.where(df['Close'] < df['bb_lower'], -1, 0))
    
    df['short_buy_signal'] = np.where((df['rsi_14'] < 30) | (df['macd'] > df['macd_signal_line']), 1, 0)
    df['short_sell_signal'] = np.where((df['rsi_14'] > 70) | (df['macd'] < df['macd_signal_line']), 1, 0)
    df['msci_rebal_month'] = df['Date'].dt.month.isin([2, 5, 8, 11]).astype(int)
    
    return df

# ---------------------------------------------------------
# 3. 데이터 파이프라인 및 모델 학습
# ---------------------------------------------------------
def run_short_term_pipeline(win: int = 10, horizon: int = 20):
    print("[시스템] DB 추출 및 데이터 병합 진행 중...")
    engine, stocks, macro, common, news, kospi_sectors, global_exclude_bases = load_mega_data_from_db()
    
    stock_names = kospi_sectors['stock_name'].dropna().unique()
    
    global_X_tr, global_y_tr = [], []
    global_X_te, global_y_te, global_base_te = [], [], []
    inf_X_list, inf_ticker_list = [], []
    
    test_indices_by_stock = {}
    current_test_idx = 0

    global_feats = None 

    for idx, s_name in enumerate(stock_names):
        target_ticker = str(kospi_sectors[kospi_sectors['stock_name'] == s_name]['ticker'].iloc[0]).replace(".0", "").strip().zfill(6)
        df = stocks[stocks['Ticker'] == target_ticker].copy()
        
        if len(df) < win + horizon + 50:
            continue

        df = apply_technical_indicators(df)
        df['Date'] = pd.to_datetime(df['Date']).astype('datetime64[ns]')
        
        df = df.merge(macro, on="Date", how="left")
        df = df.merge(common, on="Date", how="left")
        
        if not news.empty:
            news_target = news[news['Ticker'] == target_ticker].copy()
            if not news_target.empty:
                df = df.merge(news_target, on=["Date", "Ticker"], how="left")
                if 'news_score' in df.columns: df['news_score'] = df['news_score'].fillna(0)

        df = df.sort_values("Date").reset_index(drop=True)
        df['target_20d_ret'] = df['Close'].shift(-horizon) / df['Close'] - 1.0
        df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        
        drop_cols = ["Date", "Ticker", "stock_name", "Close", "target_20d_ret"]
        current_feats = [c for c in df.columns if c not in drop_cols and pd.api.types.is_numeric_dtype(df[c])]
        
        if global_feats is None: global_feats = current_feats
        for f in global_feats:
            if f not in df.columns: df[f] = 0.0

        X_base = df[global_feats].copy()
        X_lag = pd.concat([X_base.shift(lag).add_suffix(f"_lag{lag}") for lag in range(win)], axis=1)
        
        last_valid_X = X_lag.iloc[[-1]]
        inf_X_list.append(last_valid_X)
        inf_ticker_list.append(target_ticker)

        Y = df['target_20d_ret']
        bases = df['Close']
        
        idx_valid = X_lag.dropna().index.intersection(Y.dropna().index)
        X_clean = X_lag.loc[idx_valid]
        Y_clean = Y.loc[idx_valid]
        bases_clean = bases.loc[idx_valid]

        split = int(len(X_clean) * 0.8)
        train_end = split - horizon

        global_X_tr.append(X_clean.iloc[:train_end])
        global_y_tr.append(Y_clean.iloc[:train_end])
        
        te_X = X_clean.iloc[split:]
        te_Y = Y_clean.iloc[split:]
        te_base = bases_clean.iloc[split:]
        
        global_X_te.append(te_X)
        global_y_te.append(te_Y)
        global_base_te.append(te_base)
        
        te_len = len(te_X)
        test_indices_by_stock[target_ticker] = (current_test_idx, current_test_idx + te_len)
        current_test_idx += te_len

    X_train = pd.concat(global_X_tr, axis=0)
    y_train = pd.concat(global_y_tr, axis=0)
    X_test = pd.concat(global_X_te, axis=0).reset_index(drop=True)
    y_test = pd.concat(global_y_te, axis=0).reset_index(drop=True)
    base_test = pd.concat(global_base_te, axis=0).reset_index(drop=True)
    X_inf = pd.concat(inf_X_list, axis=0).reset_index(drop=True)

    print("[시스템] 데이터 병합 완료. XGBoost 모델 학습을 시작합니다.")
    params = {
        "n_estimators": 300, "max_depth": 4, "learning_rate": 0.03,
        "subsample": 0.8, "colsample_bytree": 0.8, "objective": "reg:squarederror", 
        "random_state": 42, "n_jobs": -1
    }
    
    model = XGBRegressor(**params)
    model.fit(X_train, y_train)

    # ---------------------------------------------------------
    # 4. 전체 성능 지표 및 신뢰도 평가
    # ---------------------------------------------------------
    pred_ret = model.predict(X_test)
    act_ret = y_test.values
    base_arr = base_test.values
    
    pred_prices_te = base_arr * (1.0 + pred_ret)
    act_prices_te = base_arr * (1.0 + act_ret)

    overall_dir_acc = np.mean(np.sign(pred_ret) == np.sign(act_ret)) * 100
    overall_mae = mean_absolute_error(act_prices_te, pred_prices_te)
    overall_mape = np.mean(np.abs((act_prices_te - pred_prices_te) / np.clip(act_prices_te, 1e-9, None))) * 100
    
    print("\n" + "=" * 50)
    print("[평가] 단기 모델 전체 성능 지표")
    print("-" * 50)
    print(f"방향성 적중률 (Directional Accuracy) : {overall_dir_acc:.2f}%")
    print(f"평균 절대 오차 (MAE)                 : {int(overall_mae):,} 원")
    print(f"평균 비율 오차 (MAPE)                : {overall_mape:.2f}%")
    print("=" * 50)
    
    confidence_results = []
    
    for ticker, (start_idx, end_idx) in test_indices_by_stock.items():
        if start_idx == end_idx: continue
        
        st_pred_ret = pred_ret[start_idx:end_idx]
        st_act_ret = act_ret[start_idx:end_idx]
        st_pred_price = pred_prices_te[start_idx:end_idx]
        st_act_price = act_prices_te[start_idx:end_idx]
        
        dir_acc = np.mean(np.sign(st_pred_ret) == np.sign(st_act_ret)) * 100
        mape = np.mean(np.abs((st_act_price - st_pred_price) / np.clip(st_act_price, 1e-9, None))) * 100
        mape_score = max(0, 100 - mape)
        conf_score = (dir_acc * 0.6) + (mape_score * 0.4)
        
        confidence_results.append({
            'Ticker': ticker,
            'Dir_Acc_Pct': round(dir_acc, 1),
            'MAPE_Score': round(mape_score, 1),
            'Confidence_Score': round(conf_score, 1)
        })
        
    df_conf = pd.DataFrame(confidence_results)

    # ---------------------------------------------------------
    # 5. 실전 추론 및 SHAP 지표 통합(Aggregation) 분석
    # ---------------------------------------------------------
    print("[시스템] 실전 추론 및 종목 고유 지표(통합) SHAP 분석 중...")
    inf_pred_ret = model.predict(X_inf) * 100
    
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_inf)
    
    feature_names = X_inf.columns
    positive_shap_reasons = []

    for i in range(len(X_inf)):
        sv = shap_values[i]
        
        # 기업별 지표 합산을 위한 딕셔너리
        agg_shap = {}
        
        for j, f_name in enumerate(feature_names):
            base_f = f_name.split('_lag')[0]
            
            # 매크로/공통 지표가 아닌 종목 고유 지표만 취합
            if base_f not in global_exclude_bases:
                agg_shap[base_f] = agg_shap.get(base_f, 0) + sv[j]
        
        # 합산된 총 기여도가 양수(>0)인 지표만 추출하여 내림차순 정렬
        positive_features = {k: v for k, v in agg_shap.items() if v > 0}
        sorted_features = sorted(positive_features.items(), key=lambda item: item[1], reverse=True)
        
        top_5 = sorted_features[:5]
        
        if top_5:
            reasons = [f"{k} (+{v:.3f})" for k, v in top_5]
            positive_shap_reasons.append(", ".join(reasons))
        else:
            positive_shap_reasons.append("None")

    df_final = pd.DataFrame({
        'Ticker': inf_ticker_list,
        'Expected_Return(%)': np.round(inf_pred_ret, 2),
        'Top_5_Positive_Factors': positive_shap_reasons
    })
    
    df_final = pd.merge(df_final, df_conf, on='Ticker', how='left')
    df_final['Confidence_Score'] = df_final['Confidence_Score'].fillna(50.0)
    df_final = df_final.sort_values(by='Expected_Return(%)', ascending=False).reset_index(drop=True)

    print("\n" + "=" * 100)
    print(f"[결과] 단기(20일) 예측 및 신뢰도 리포트 (통합 SHAP 기준)")
    print("=" * 100)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df_final.to_string(index=False))

if __name__ == "__main__":
    run_short_term_pipeline(win=10, horizon=20)