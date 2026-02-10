import os
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv
from pandas.tseries.offsets import DateOffset

# ============================================================
# [SECTION 1] 설정 및 기간 확장
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'

# 철강/소재 섹터 주요 종목
MAT_STOCKS = {
    '고려아연': '010130', 'POSCO홀딩스': '005490', '현대제철': '004020',
    '풍산': '103140', '세아베스틸지주': '001430', '영풍': '000670',
    '동원시스템즈': '016670', '율촌화학': '008730', '아세아': '002030',
    '세아제강지주': '003030'
}

# 지표 안정성을 위해 2021년부터 충분히 수집
FETCH_START_DATE = '2021-01-01'
START_YM = '202101'

# ============================================================
# [SECTION 2] Helper 함수 (Dtype 고정 및 로그 유지)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"
    def __init__(self):
        self.api_key = os.getenv("ECOS_API_KEY")

    def fetch_data(self, stat_code, item_code, start, end):
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/500/{stat_code}/M/{start}/{end}/{item_code}"
        try:
            resp = requests.get(url).json()
            rows = resp.get("StatisticSearch", {}).get("row", [])
            if not rows: return pd.DataFrame(columns=['Date', 'Value'])
            df = pd.DataFrame(rows)
            df['Date'] = pd.to_datetime(df['TIME'], format='%Y%m').dt.normalize()
            df['Value'] = pd.to_numeric(df['DATA_VALUE'])
            return df[['Date', 'Value']].sort_values('Date').drop_duplicates('Date')
        except: return pd.DataFrame(columns=['Date', 'Value'])

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    try:
        df = fdr.DataReader(ticker, start, end)
        if df is None or df.empty: return pd.DataFrame(columns=['Date', col_name])
        df = df.reset_index()
        df.columns = ['Date' if c.upper() == 'DATE' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        df = df[['Date', val_col]].rename(columns={val_col: col_name})
        return df.sort_values('Date').drop_duplicates('Date')
    except: return pd.DataFrame(columns=['Date', col_name])

# ============================================================
# [SECTION 3] 데이터 수집 및 통합 (MergeError & KeyError 방어)
# ============================================================
def fetch_materials_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 수집
    stock_list = []
    for name, ticker in MAT_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 공식 지표 수집
    print("📡 ECOS 제조업 생산지수(I11AC) 수집 중...")
    mfg_df = ecos.fetch_data('901Y032', 'I11AC', START_YM, '202512')
    
    print("📡 ECOS 선행종합지수(I16A) 수집 중...")
    cli_df = ecos.fetch_data('901Y067', 'I16A', START_YM, '202512')

    # [수정] 파일 분석 결과에 따른 철강 1차 제품(3071AA) PPI 수집
    print("📡 ECOS 철강 1차 제품 PPI(3071AA) 수집 중...")
    steel_ppi_df = ecos.fetch_data('404Y014', '3071AA', START_YM, '202512')

    # 매크로 가공
    macro_df = pd.DataFrame(columns=['Date'])
    if not mfg_df.empty:
        mfg_df['mfg_lag3'] = mfg_df['Value'].shift(3)
        macro_df = mfg_df[['Date', 'mfg_lag3']]

    if not cli_df.empty:
        cli_df['cli_lag'] = cli_df['Value'].shift(3)
        if macro_df.empty: macro_df = cli_df[['Date', 'cli_lag']]
        else: macro_df = pd.merge(macro_df, cli_df[['Date', 'cli_lag']], on='Date', how='outer')

    if not steel_ppi_df.empty:
        steel_ppi_df = steel_ppi_df.rename(columns={'Value': 'steel_ppi'})
        if macro_df.empty: macro_df = steel_ppi_df[['Date', 'steel_ppi']]
        else: macro_df = pd.merge(macro_df, steel_ppi_df[['Date', 'steel_ppi']], on='Date', how='outer')

    # 3. 원자재 및 글로벌 지표 수집
    print("📡 원자재(구리, WTI) 및 FXI/Steel ETF 수집 중...")
    copper = yf.download('HG=F', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    copper.columns = ['Date', 'Copper_Close']
    wti = yf.download('CL=F', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    wti.columns = ['Date', 'WTI_Close']
    fxi = yf.download('FXI', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    fxi.columns = ['Date', 'FXI_Close']
    steel_etf = safe_fetch_fdr('117680', FETCH_START_DATE, END_DATE, 'Steel_Close')

    # 병합 직전 타입 강제 동기화 (MergeError 방지)
    def force_sync_date(df):
        if df is not None and not df.empty and 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize()
            df['Date'] = pd.to_datetime(df['Date'].astype(str)).astype('<M8[ns]')
            return df.sort_values('Date').reset_index(drop=True)
        return df

    full_stocks = force_sync_date(full_stocks)
    copper, wti, fxi = [force_sync_date(d) for d in [copper, wti, fxi]]
    steel_etf = force_sync_date(steel_etf)
    macro_df = force_sync_date(macro_df)

    # 시계열 병합
    merged = pd.merge_asof(full_stocks, copper, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge_asof(merged, wti, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge_asof(merged, fxi, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge(merged, steel_etf, on='Date', how='left')
    
    if not macro_df.empty:
        merged = pd.merge_asof(merged, macro_df, on='Date', direction='backward')

    # 안전하게 존재하는 컬럼만 선별하여 결측치 보정 (KeyError 방지)
    fill_cols = ['Copper_Close', 'WTI_Close', 'FXI_Close', 'Steel_Close', 'steel_ppi', 'mfg_lag3', 'cli_lag']
    existing_fill_cols = [c for c in fill_cols if c in merged.columns]
    
    merged = merged.sort_values(['Stock_Name', 'Date'])
    if existing_fill_cols:
        merged[existing_fill_cols] = merged.groupby('Stock_Name')[existing_fill_cols].ffill()
        merged[existing_fill_cols] = merged.groupby('Stock_Name')[existing_fill_cols].bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산 (Steel Beta 유효성 강화)
# ============================================================
def calculate_materials_metrics(group):
    group = group.sort_values('Date')
    s_ret = group['Close'].pct_change()
    
    # 1. 중국 경기 모멘텀 (FXI 기반)
    group['china_momentum'] = group['FXI_Close'].pct_change(20)
    
    # 2. 원자재 및 에너지 베타 (60일)
    c_ret = group['Copper_Close'].pct_change()
    w_ret = group['WTI_Close'].pct_change()
    group['copper_beta'] = s_ret.rolling(60, min_periods=40).cov(c_ret) / (c_ret.rolling(60, min_periods=40).var() + 1e-10)
    group['wti_beta'] = s_ret.rolling(60, min_periods=40).cov(w_ret) / (w_ret.rolling(60, min_periods=40).var() + 1e-10)
    
    # 3. [수정] 철강 베타 (Steel PPI 기반)
    # 월간 지표의 특성을 고려하여 min_periods를 조정해 0값 도배 방지
    if 'steel_ppi' in group.columns:
        p_ret = group['steel_ppi'].pct_change()
        # 월간 데이터의 변화가 적으므로 윈도우 내 유효한 변화가 조금만 있어도 베타 계산
        group['steel_beta'] = s_ret.rolling(60, min_periods=5).cov(p_ret) / (p_ret.rolling(60, min_periods=5).var() + 1e-10)
        group['steel_beta'] = group['steel_beta'].replace([np.inf, -np.inf], np.nan).ffill().fillna(0).clip(-5, 5)
    else:
        group['steel_beta'] = 0

    # 4. 산업 Z-score (120일)
    rel_price = group['Close'] / (group['Steel_Close'] + 1e-9)
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_materials_data()
    
    if not df_raw.empty:
        print("🚀 철강/소재 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_materials_metrics)
        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # 최종 컬럼 구성
        final_cols = [
            'Date', 'Ticker', 'Stock_Name', 'Close', 
            'china_momentum', 'mfg_lag3', 'cli_lag', 
            'copper_beta', 'wti_beta', 'steel_beta', 'z_score'
        ]
        actual_cols = [c for c in final_cols if c in df_final.columns]
        df_final = df_final[actual_cols].fillna(0)

        df_final.to_csv('materials_processed.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 철강 PPI(3071) 및 베타 산출 완료: materials_processed.csv (총 {len(df_final)}행)")
        print(df_final.head(10))