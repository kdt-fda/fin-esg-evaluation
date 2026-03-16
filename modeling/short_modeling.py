import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import pymysql
import shap
import concurrent.futures

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
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_name = os.environ.get('DB_NAME')
    
    if not all([db_host, db_port, db_user, db_password, db_name]):
        raise ValueError("[시스템 오류] DB 환경변수가 설정되지 않았습니다.")
    
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
    global_exclude_bases = set(macro_cols + common_cols + ['msci_event'])
    
    return engine, stocks, macro, common, news, kospi_sectors, global_exclude_bases

# ---------------------------------------------------------
# 2. 기술적 지표 생성
# ---------------------------------------------------------
def apply_technical_indicators(df):
    df = df.sort_values('Date').copy()
    
    df['ma5'] = df['Close'].rolling(window=5).mean()
    df['ma20'] = df['Close'].rolling(window=20).mean()
    
    df['golden_cross_5_20'] = np.where((df['ma5'].shift(1) < df['ma20'].shift(1)) & (df['ma5'] >= df['ma20']), 1, 0)
    df['death_cross_5_20'] = np.where((df['ma5'].shift(1) > df['ma20'].shift(1)) & (df['ma5'] <= df['ma20']), 1, 0)

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    std_20 = df['Close'].rolling(window=20).std()
    df['bb_upper'] = df['ma20'] + (std_20 * 2)
    df['bb_lower'] = df['ma20'] - (std_20 * 2)
    df['bb_breakout'] = np.where(df['Close'] > df['bb_upper'], 1, np.where(df['Close'] < df['bb_lower'], -1, 0))
    
    df['msci_event'] = df['Date'].dt.month.isin([2, 5, 8, 11]).astype(int)
    
    return df

# ---------------------------------------------------------
# 3. 데이터 파이프라인 및 멀티쓰레딩/GPU 모델 학습
# ---------------------------------------------------------
def run_short_term_pipeline(win: int = 10, horizon: int = 20):
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
        
        if len(df) < win + horizon + 50: continue

        df = apply_technical_indicators(df)
        df['Date'] = pd.to_datetime(df['Date']).astype('datetime64[ns]')
        
        df = df.merge(macro, on="Date", how="left").merge(common, on="Date", how="left")
        
        if not news.empty:
            news_target = news[news['Ticker'] == target_ticker].copy()
            if not news_target.empty:
                df = df.merge(news_target, on=["Date", "Ticker"], how="left")
                if 'news_score' in df.columns: df['news_score'] = df['news_score'].fillna(0)

        df = df.sort_values("Date").reset_index(drop=True)
        
        target_cols = []
        for h in range(1, horizon + 1):
            col_name = f'target_{h}d_ret'
            df[col_name] = df['Close'].shift(-h) / df['Close'] - 1.0
            target_cols.append(col_name)
            
        df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        
        drop_cols = ["Date", "Ticker", "stock_name", "Close"] + target_cols
        current_feats = [c for c in df.columns if c not in drop_cols and pd.api.types.is_numeric_dtype(df[c])]
        
        if global_feats is None: global_feats = current_feats
        for f in global_feats:
            if f not in df.columns: df[f] = 0.0

        X_base = df[global_feats].copy()
        X_lag = pd.concat([X_base.shift(lag).add_suffix(f"_lag{lag}") for lag in range(win)], axis=1)
        
        last_valid_X = X_lag.iloc[[-1]]
        inf_X_list.append(last_valid_X)
        inf_ticker_list.append(target_ticker)

        Y = df[target_cols]
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

    use_gpu = False
    params = {
        "n_estimators": 300, "max_depth": 4, "learning_rate": 0.03,
        "subsample": 0.8, "colsample_bytree": 0.8, "objective": "reg:squarederror", 
        "random_state": 42
    }
    
    try:
        tmp = XGBRegressor(tree_method='hist', device='cuda', n_estimators=1)
        tmp.fit(np.array([[0.0]]), np.array([0.0]))
        use_gpu = True
        params['tree_method'] = 'hist'
        params['device'] = 'cuda'
    except Exception:
        params['tree_method'] = 'hist' 

    cpu_cores = os.cpu_count() or 4
    max_workers = 4 if use_gpu else min(4, max(1, cpu_cores // 2))
    params['n_jobs'] = max(1, cpu_cores // max_workers) if not use_gpu else -1
    
    models = [None] * horizon

    def train_target_model(h):
        m = XGBRegressor(**params)
        m.fit(X_train, y_train.iloc[:, h])
        return h, m

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(train_target_model, h) for h in range(horizon)]
        for future in concurrent.futures.as_completed(futures):
            h, m = future.result()
            models[h] = m

# ---------------------------------------------------------
# 4. 전체 성능 지표 및 신뢰도 평가
# ---------------------------------------------------------
    pred_ret_all = np.column_stack([m.predict(X_test) for m in models])
    pred_ret_20d = pred_ret_all[:, -1]
    act_ret_20d = y_test.iloc[:, -1].values
    base_arr = base_test.values
    
    pred_prices_te = base_arr * (1.0 + pred_ret_20d)
    act_prices_te = base_arr * (1.0 + act_ret_20d)

    confidence_results = []
    
    for ticker, (start_idx, end_idx) in test_indices_by_stock.items():
        if start_idx == end_idx: continue
        
        st_pred_ret = pred_ret_20d[start_idx:end_idx]
        st_act_ret = act_ret_20d[start_idx:end_idx]
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
# 5. 실전 추론 및 SHAP 분석
# ---------------------------------------------------------
    inf_pred_ret_all = np.column_stack([m.predict(X_inf) for m in models])
    inf_pred_ret_20d = inf_pred_ret_all[:, -1] * 100  
    
    model_20d = models[-1]
    explainer = shap.TreeExplainer(model_20d)
    shap_values = explainer.shap_values(X_inf)
    
    feature_names = X_inf.columns
    positive_shap_reasons = []

    for i in range(len(X_inf)):
        sv = shap_values[i]
        agg_shap = {}
        for j, f_name in enumerate(feature_names):
            base_f = f_name.split('_lag')[0]
            if base_f not in global_exclude_bases:
                agg_shap[base_f] = agg_shap.get(base_f, 0) + sv[j]
        
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
        'Expected_Return_20d(%)': np.round(inf_pred_ret_20d, 2),
        'Forecast_Path(%)': [np.round(path * 100, 2).tolist() for path in inf_pred_ret_all],
        'Top_5_Positive_Factors': positive_shap_reasons
    })
    
    df_final = pd.merge(df_final, df_conf, on='Ticker', how='left')
    df_final['Confidence_Score'] = df_final['Confidence_Score'].fillna(50.0)
    df_final = df_final.sort_values(by='Expected_Return_20d(%)', ascending=False).reset_index(drop=True)

    return df_final

if __name__ == "__main__":
    df_result = run_short_term_pipeline(win=10, horizon=20)