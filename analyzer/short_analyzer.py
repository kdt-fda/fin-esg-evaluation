import os
import json
import pandas as pd
import numpy as np
import pymysql
import shap
import concurrent.futures
from dotenv import load_dotenv

from xgboost import XGBRegressor
import warnings
warnings.filterwarnings('ignore')

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

# =========================================================================
# 2. 메인 파이프라인
# =========================================================================
def run_short_term_pipeline(win: int = 10, horizon: int = 20):
    print("🚀 단기 예측 모델 파이프라인 가동 (GPU/병렬처리 적용)...")
    
    joiner = StockDataJoiner()
    selector = FeatureSelector()
    
    conn = _connect()
    try:
        kospi_df = pd.read_sql("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB", conn)

        # SHAP 분석 시 공통 파생 지표 제외
        common_df = pd.read_sql("SELECT * FROM COMMON_TB LIMIT 1", conn)
        
        common_cols = [c for c in common_df.columns if c not in ['trade_date', 'date']]
        global_exclude_bases = set(common_cols + ['msci_event'])
    finally:
        conn.close()
    
    stock_names = kospi_df['stock_name'].dropna().unique()
    
    global_X_tr, global_y_tr = [], []
    global_X_te, global_y_te, global_base_te = [], [], []
    inf_X_list, inf_ticker_list = [], []
    test_indices_by_stock = {}
    current_test_idx = 0
    latest_date = None

    print(f"[1/5] 총 {len(stock_names)}개 종목 데이터 병합 및 피처 세팅 중...")
    
    for s_name in stock_names:
        # StockDataJoiner 호출
        df = joiner.get_modeling_dataset(s_name)
        
        if df is None or len(df) < win + horizon + 50:
            continue
            
        ticker = zfill6([df['ticker'].iloc[0]])
        df = df.sort_values('trade_date').reset_index(drop=True)
        
        if latest_date is None or df['trade_date'].max() > latest_date:
            latest_date = df['trade_date'].max()
            
        # 20일치 타겟 동시 생성
        target_cols = []
        for i in range(1, horizon + 1):
            col_name = f'target_{i}d'
            df[col_name] = df['close'].shift(-i) / df['close'] - 1.0
            target_cols.append(col_name)

        # FeatureSelector 호출
        X_base_raw = selector.get_features(df, mode='short')

        ignore_cols = ['trade_date', 'ticker', 'stock_name', 'close']
        num_feats = [c for c in X_base_raw.columns if pd.api.types.is_numeric_dtype(X_base_raw[c]) and c not in ignore_cols]
        
        X_base_raw = X_base_raw[num_feats]
        X_base_raw = X_base_raw.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        
        # Lag 피처 생성
        X_lag = pd.concat([X_base_raw.shift(lag).add_suffix(f"_lag{lag}") for lag in range(win)], axis=1)
        
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

    print(f"[2/5] XGBoost GPU 감지 및 {horizon}개 모델 병렬 학습 시작 (학습 샘플: {len(X_train)}건)...")
    
    use_gpu = False
    params = {
        "n_estimators": 200, "max_depth": 4, "learning_rate": 0.03,
        "subsample": 0.8, "colsample_bytree": 0.8, "objective": "reg:squarederror", 
        "random_state": 42
    }
    
    # GPU(CUDA) 테스트
    try:
        tmp = XGBRegressor(tree_method='hist', device='cuda', n_estimators=1)
        tmp.fit(np.array([[0.0]]), np.array([0.0]))
        use_gpu = True
        params['tree_method'] = 'hist'
        params['device'] = 'cuda'
        print("  -> CUDA GPU 가속 활성화됨!")
    except Exception:
        params['tree_method'] = 'hist' 
        print("  -> CPU 모드로 학습 진행.")

    # 스레드 동적 할당
    cpu_cores = os.cpu_count() or 4
    max_workers = 4 if use_gpu else min(4, max(1, cpu_cores // 2))
    params['n_jobs'] = max(1, cpu_cores // max_workers) if not use_gpu else -1
    
    models = [None] * horizon

    def train_target_model(h):
        # h번째 타겟을 맞히는 전용 모델 생성
        m = XGBRegressor(**params)
        m.fit(X_train, y_train.iloc[:, h])
        return h, m

    # 병렬 처리로 20개 모델 동시 학습
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(train_target_model, h) for h in range(horizon)]
        for future in concurrent.futures.as_completed(futures):
            h, m = future.result()
            models[h] = m

    print("[3/5] Test Set 기반 백테스트 및 신뢰도(Confidence) 산출 중...")
    # 20개 모델의 예측값을 옆으로 이어 붙임 (MultiOutputRegressor와 동일한 형태)
    pred_all_te = np.column_stack([m.predict(X_test) for m in models])
    
    pred_ret_20d = pred_all_te[:, -1] 
    act_ret_20d = y_test.iloc[:, -1].values
    
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
    inf_preds_20d = np.column_stack([m.predict(X_inf) for m in models]) * 100
    
    # SHAP는 20일 차 모델(models[-1]) 기준으로 분석
    explainer = shap.TreeExplainer(models[-1])
    shap_values = explainer.shap_values(X_inf)
    
    db_insert_data = []
    for i in range(len(X_inf)):
        ticker = inf_ticker_list[i]
        sv = shap_values[i]
        
        trajectory = [round(float(val), 2) for val in inf_preds_20d[i]]
        
        agg_shap = {}
        for j, f_name in enumerate(X_inf.columns):
            base_f = f_name.split('_lag')[0]
            # 공통 파생 지표는 SHAP Top 요인에서 제외
            if base_f not in global_exclude_bases:
                agg_shap[base_f] = agg_shap.get(base_f, 0) + sv[j]
            
        # 긍정 Top 3 / 부정 Top 3
        pos_feats = sorted([(k, v) for k, v in agg_shap.items() if v > 0], key=lambda x: x[1], reverse=True)[:3]
        neg_feats = sorted([(k, v) for k, v in agg_shap.items() if v < 0], key=lambda x: x[1])[:3]
        
        combined_feats = pos_feats + neg_feats
        top_feat_names = [item[0] for item in combined_feats]
        top_feat_vals = [round(float(item[1]), 4) for item in combined_feats]
        
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