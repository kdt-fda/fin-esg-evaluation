import os
import FinanceDataReader as fdr
import pandas as pd
import numpy as np

# ============================================================
# [SECTION 1] 설정
# ============================================================
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
FETCH_START_DATE = '2021-01-01' # 윈도우 확보

HEAL_STOCKS = {
    '삼성바이오로직스': '207940', '셀트리온': '068270', 'SK바이오팜': '326030', 
    '유한양행': '000100', '한미약품': '128940', 'SK바이오사이언스': '302440', 
    '한미사이언스': '008930', '한올바이오파마': '009420', '녹십자': '006280',
    '대웅제약': '069620', '대웅': '003090', '종근당': '185750', 
    '에스디바이오센서': '137310', '녹십자홀딩스': '005250'
}

# ============================================================
# [SECTION 2] 데이터 통합 함수 (중복 원천 차단)
# ============================================================
def fetch_healthcare_data():
    # 1. 거시 지표 미리 준비 (날짜 기준)
    kospi200 = fdr.DataReader('KS200', FETCH_START_DATE, END_DATE)[['Close']].reset_index()
    kospi200.columns = ['Date', 'KOSPI200_Close']
    tiger_hc = fdr.DataReader('227540', FETCH_START_DATE, END_DATE)[['Close']].reset_index()
    tiger_hc.columns = ['Date', 'TigerHC_Close']
    
    macro_df = pd.merge(kospi200, tiger_hc, on='Date', how='outer').sort_values('Date').ffill()
    macro_df['Date'] = pd.to_datetime(macro_df['Date']).dt.normalize()

    # 2. 재무 데이터 준비 (2022~2025)
    funda_list = []
    for y in [2022, 2023, 2024, 2025]:
        for q in [1, 2, 3, 4]:
            f = f'fundamental_{y}_Q{q}.csv'
            if os.path.exists(f):
                tmp = pd.read_csv(f)[['end_date', '종목명', 'pbr', 'revenue']]
                funda_list.append(tmp)
    
    df_funda = pd.concat(funda_list).rename(columns={'end_date': 'Date', '종목명': 'Stock_Name'})
    df_funda['Stock_Name'] = df_funda['Stock_Name'].str.strip()
    df_funda['Date'] = pd.to_datetime(df_funda['Date']).dt.normalize()
    
    # 3. R&D 데이터 준비
    rnd = pd.read_csv('RND.csv')[['end_date', '종목명', 'rnd_expense']]
    rnd = rnd.rename(columns={'end_date': 'Date', '종목명': 'Stock_Name'})
    rnd['Stock_Name'] = rnd['Stock_Name'].str.strip()
    rnd['Date'] = pd.to_datetime(rnd['Date']).dt.normalize()
    
    # 재무 + R&D 통합
    df_funda_merged = pd.merge(df_funda, rnd, on=['Date', 'Stock_Name'], how='outer')
    df_funda_merged['rnd_ratio'] = (df_funda_merged['rnd_expense'] / (df_funda_merged['revenue'] + 1e-9)) * 100

    # 4. 종목별 주가에 데이터 매칭 (핵심: Loop 방식)
    final_stock_list = []
    for name, ticker in HEAL_STOCKS.items():
        print(f"📡 {name}({ticker}) 처리 중...")
        # 주가 수집
        price_df = fdr.DataReader(ticker, FETCH_START_DATE, END_DATE).reset_index()
        price_df.columns = [c.capitalize() if c.lower() == 'date' else c for c in price_df.columns]
        price_df['Date'] = pd.to_datetime(price_df['Date']).dt.normalize()
        price_df['Ticker'], price_df['Stock_Name'] = ticker, name
        
        # 거시 지표 병합 (날짜 기준)
        merged = pd.merge(price_df, macro_df, on='Date', how='left')
        
        # 재무 지표 병합 (ASOF 사용 - 가장 가까운 과거 분기 데이터 매칭)
        stock_funda = df_funda_merged[df_funda_merged['Stock_Name'] == name].sort_values('Date')
        if not stock_funda.empty:
            merged = pd.merge_asof(merged.sort_values('Date'), stock_funda, 
                                   on='Date', by='Stock_Name', direction='backward')
        
        # 결측치 채우기 (해당 종목 내에서만)
        fill_cols = ['KOSPI200_Close', 'TigerHC_Close', 'pbr', 'rnd_ratio']
        merged[fill_cols] = merged[fill_cols].ffill().bfill()
        
        # 지표 계산
        merged = calculate_metrics(merged)
        final_stock_list.append(merged)
    
    return pd.concat(final_stock_list).reset_index(drop=True)

# ============================================================
# [SECTION 3] 지표 계산 함수
# ============================================================
def calculate_metrics(group):
    s_ret = group['Close'].pct_change()
    
    # 1. PBR Z-score
    if 'pbr' in group.columns:
        rolling_mean = group['pbr'].rolling(window=120, min_periods=30).mean()
        rolling_std = group['pbr'].rolling(window=120, min_periods=30).std()
        group['pbr_zscore'] = (group['pbr'] - rolling_mean) / (rolling_std + 1e-9)
        group['is_pbr_overheated'] = (group['pbr_zscore'] > 2).astype(float)
    
    # 2. 변동성 비율
    if 'KOSPI200_Close' in group.columns:
        k_ret = group['KOSPI200_Close'].pct_change()
        v_stock = s_ret.rolling(20, min_periods=10).std()
        v_market = k_ret.rolling(20, min_periods=10).std()
        group['vol_ratio'] = v_stock / (v_market + 1e-10)
        group['is_high_vol_stock'] = (group['vol_ratio'] > 1.5).astype(float)
    
    # 3. 산업 Z-score
    if 'TigerHC_Close' in group.columns:
        rel_price = group['Close'] / (group['TigerHC_Close'] + 1e-9)
        group['z_score'] = (rel_price - rel_price.rolling(120, min_periods=30).mean()) / \
                           (rel_price.rolling(120, min_periods=30).std() + 1e-9)
    return group

# ============================================================
# [SECTION 4] 실행
# ============================================================
if __name__ == "__main__":
    df_final = fetch_healthcare_data()
    
    # 사용자 시작일로 필터링
    df_final = df_final[df_final['Date'] >= USER_START_DATE].copy()
    
    # 불필요한 컬럼 제거 (원본 revenue, rnd_expense 등)
    final_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'rnd_ratio', 
                  'pbr_zscore', 'is_pbr_overheated', 'vol_ratio', 'is_high_vol_stock', 'z_score']
    df_final = df_final[[c for c in final_cols if c in df_final.columns]]

    df_final.to_csv('healthcare_processed.csv', index=False, encoding='utf-8-sig')
    print("✅ 모든 문제(중복, 가격혼선, 결측치) 해결 완료!")
    print(df_final.head(10))