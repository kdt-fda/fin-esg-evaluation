import os
import json
import pandas as pd
import numpy as np
import pymysql
import shap
from dotenv import load_dotenv

from xgboost import XGBRegressor
from sklearn.multioutput import MultiOutputRegressor
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

# =========================================================================
# 2. 단기 예측 메인 파이프라인
# =========================================================================
def run_short_term_pipeline(win: int = 10, horizon: int = 20):
    print("🚀 단기 예측 모델 파이프라인 가동...")
    
    joiner = StockDataJoiner()
    selector = FeatureSelector()
    
    # 1. KOSPI 200 종목 가져오기
    conn = _connect()
    try:
        kospi_df = pd.read_sql("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB", conn)
    finally:
        conn.close()
    
    stock_names = kospi_df['stock_name'].dropna().unique()
    
    global_X_tr, global_y_tr = [], []
    global_X_te, global_y_te, global_base_te = [], []
    inf_X_list, inf_ticker_list = [], []
    test_indices_by_stock = {}
    current_test_idx = 0
    latest_date = None

    print(f"[1/5] 총 {len(stock_names)}개 종목 데이터 병합 및 피처 세팅 중...")
    
    for s_name in stock_names:
        # 1. Joiner로 기본 데이터 로드
        df = joiner.get_modeling_dataset(s_name)
        
        if df is None or len(df) < win + horizon + 50:
            continue
            
        ticker = zfill6(pd.Series([df['ticker'].iloc[0]]))[0]
        df = df.sort_values('trade_date').reset_index(drop=True)
        
        if latest_date is None or df['trade_date'].max() > latest_date:
            latest_date = df['trade_date'].max()
            
        # 2. 20일치 궤적 타겟 동시 생성
        target_cols = []
        for i in range(1, horizon + 1):
            col_name = f'target_{i}d'
            df[col_name] = df['close'].shift(-i) / df['close'] - 1.0
            target_cols.append(col_name)

        # 3. FeatureSelector로 필요한 변수만 추출
        X_base_raw = selector.get_features(df, mode='short')
        X_base_raw = X_base_raw.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        
        # 4. Lag 피처 생성
        X_lag = pd.concat([X_base_raw.shift(lag).add_suffix(f"_lag{lag}") for lag in range(win)], axis=1)
        
        # 실전 추론용(최신일자) 데이터 저장
        inf_X_list.append(X_lag.iloc[[-1]])
        inf_ticker_list.append(ticker)
        
        Y_targets = df[target_cols]
        bases = df['close']
        
        idx_valid = X_lag.dropna().index.intersection(Y_targets.dropna().index)
        X_clean = X_lag.loc[idx_valid]
        Y_clean = Y_targets.loc[idx_valid]
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
        test_indices_by_stock[ticker] = (current_test_idx, current_test_idx + te_len)
        current_test_idx += te_len

    X_train = pd.concat(global_X_tr, axis=0)
    y_train = pd.concat(global_y_tr, axis=0)
    X_test = pd.concat(global_X_te, axis=0).reset_index(drop=True)
    y_test = pd.concat(global_y_te, axis=0).reset_index(drop=True)
    base_test = pd.concat(global_base_te, axis=0).reset_index(drop=True)
    X_inf = pd.concat(inf_X_list, axis=0).reset_index(drop=True)

    print(f"[2/5] MultiOutput XGBoost 학습 시작 (학습 샘플: {len(X_train)}건)...")
    base_model = XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8, objective="reg:squarederror", 
        random_state=42, n_jobs=-1
    )
    multi_model = MultiOutputRegressor(base_model)
    multi_model.fit(X_train, y_train)

    print("[3/5] Test Set 기반 백테스트 및 신뢰도(Confidence) 산출 중...")
    pred_all_te = multi_model.predict(X_test)
    
    pred_ret_20d = pred_all_te[:, -1] 
    act_ret_20d = y_test[f'target_{horizon}d'].values
    
    pred_prices_te = base_test.values * (1.0 + pred_ret_20d)
    act_prices_te = base_test.values * (1.0 + act_ret_20d)

    conf_list = []
    for ticker, (start_idx, end_idx) in test_indices_by_stock.items():
        if start_idx == end_idx: continue
        
        st_pred_ret = pred_ret_20d[start_idx:end_idx]
        st_act_ret = act_ret_20d[start_idx:end_idx]
        
        dir_acc = np.mean(np.sign(st_pred_ret) == np.sign(st_act_ret)) * 100
        
        st_pred_price = pred_prices_te[start_idx:end_idx]
        st_act_price = act_prices_te[start_idx:end_idx]
        mape = np.mean(np.abs((st_act_price - st_pred_price) / np.clip(st_act_price, 1e-9, None))) * 100
        
        mape_score = max(0, 100 - mape)
        conf_score = (dir_acc * 0.6) + (mape_score * 0.4)
        
        conf_list.append({'ticker': ticker, 'dir_acc': round(dir_acc, 1), 'mape': round(mape, 2), 'conf_score': round(conf_score, 1)})
        
    df_conf = pd.DataFrame(conf_list).set_index('ticker')

    print(f"[4/5] {latest_date.date()} 기준 실전 추론 및 SHAP 요인 분석...")
    inf_preds_20d = multi_model.predict(X_inf) * 100
    
    explainer = shap.TreeExplainer(multi_model.estimators_[-1])
    shap_values = explainer.shap_values(X_inf)
    
    db_insert_data = []
    for i in range(len(X_inf)):
        ticker = inf_ticker_list[i]
        sv = shap_values[i]
        
        trajectory = [round(float(val), 2) for val in inf_preds_20d[i]]
        
        agg_shap = {}
        for j, f_name in enumerate(X_inf.columns):
            base_f = f_name.split('_lag')[0]
            agg_shap[base_f] = agg_shap.get(base_f, 0) + sv[j]
            
        positive_features = {k: v for k, v in agg_shap.items() if v > 0}
        sorted_features = sorted(positive_features.items(), key=lambda item: item[1], reverse=True)[:5]
        
        top_feat_names = [item[0] for item in sorted_features]
        top_feat_vals = [round(float(item[1]), 4) for item in sorted_features]
        
        conf_data = df_conf.loc[ticker] if ticker in df_conf.index else pd.Series({'dir_acc': 50.0, 'mape': 5.0, 'conf_score': 50.0})

        db_insert_data.append(
            (
                latest_date.date(), ticker,
                json.dumps(trajectory), json.dumps(top_feat_names), json.dumps(top_feat_vals),
                conf_data['dir_acc'], conf_data['mape'], conf_data['conf_score']
            )
        )

    print(f"[5/5] SHORT_PRED_TB 적재 중... (총 {len(db_insert_data)}건)")
    conn = _connect()
    try:
        cur = conn.cursor()
        sql = """
            INSERT INTO SHORT_PRED_TB (
                pred_date, ticker, prediction, shap_feature, shap_value, dir_acc, mape, conf_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                prediction=VALUES(prediction), shap_feature=VALUES(shap_feature),
                shap_value=VALUES(shap_value), dir_acc=VALUES(dir_acc),
                mape=VALUES(mape), conf_score=VALUES(conf_score);
        """
        cur.executemany(sql, db_insert_data)
        conn.commit()
        print("✅ 단기 예측 결과 업데이트 완료")
    except Exception as e:
        print(f"❌ DB 적재 오류: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_short_term_pipeline()