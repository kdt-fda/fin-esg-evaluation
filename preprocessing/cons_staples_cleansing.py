import os
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import DateOffset
import requests
from dotenv import load_dotenv

# ============================================================
# [SECTION 1] 설정 및 기간 확장
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'

STAPLES_STOCKS = {
    '한국전력': '015760', 'KT&G': '033780', '에이피알': '278470', '삼양식품': '003230',
    '아모레퍼시픽': '090430', 'CJ': '001040', '오리온': '271560', 'LG생활건강': '051900',
    '한국가스공사': '036460', 'CJ제일제당': '097950', '롯데지주': '004990', '이마트': '139480',
    '농심': '004370', '동서': '026960', '아모레퍼시픽홀딩스': '002790', '코스맥스': '192820',
    'BGF리테일': '282330', '동원산업': '006040', 'GS리테일': '007070', '한국콜마': '161890',
    '오뚜기': '007310', '오리온홀딩스': '001800', '롯데칠성': '005300', '지역난방공사': '071320',
    '하이트진로': '000080', '롯데웰푸드': '280360', '대상': '001680'
}

FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - DateOffset(months=24)).strftime('%Y-%m-%d')
ECOS_START_YM = (pd.to_datetime(USER_START_DATE) - DateOffset(months=30)).strftime('%Y%m')

# ============================================================
# [SECTION 2] Helper 및 수집 함수
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"
    def __init__(self):
        self.api_key = os.getenv("ECOS_API_KEY")

    def fetch_data(self, stat_code, item_code, start, end):
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/1000/{stat_code}/M/{start}/{end}/{item_code}"
        try:
            resp = requests.get(url).json()
            rows = resp.get("StatisticSearch", {}).get("row", [])
            if not rows: return pd.DataFrame()
            df = pd.DataFrame(rows)
            df['Date'] = pd.to_datetime(df['TIME'], format='%Y%m').dt.normalize()
            df['Value'] = pd.to_numeric(df['DATA_VALUE'])
            return df[['Date', 'Value']].sort_values('Date')
        except: return pd.DataFrame()

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    try:
        df = fdr.DataReader(ticker, start, end)
        if df is None or df.empty: return pd.DataFrame()
        df.index.name = 'Date'
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        return df[['Date', val_col]].rename(columns={val_col: col_name})
    except: return pd.DataFrame()

# ============================================================
# [SECTION 3] 데이터 수집 및 통합 (CLI 제외)
# ============================================================
def fetch_cons_staples_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 수집
    stock_list = []
    for name, ticker in STAPLES_STOCKS.items():
        print(f"📡 {name}({ticker}) 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 공식 매크로 지표 수집
    print("📡 ECOS 공식 지표(CSI, CPI) 수집 중...")
    # 소비자심리지수: 511Y002 -> FME
    csi_raw = ecos.fetch_data('511Y002', 'FME', ECOS_START_YM, '202512')
    # 소비자물가지수: 901Y009 -> 0
    cpi_raw = ecos.fetch_data('901Y009', '0', ECOS_START_YM, '202512')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not csi_raw.empty:
        csi_raw['csi_sentiment'] = csi_raw['Value'].shift(3) 
        macro_df = csi_raw[['Date', 'csi_sentiment']].copy()
    if not cpi_raw.empty:
        cpi_raw['cpi_yoy'] = cpi_raw['Value'].pct_change(12)
        if macro_df.empty: macro_df = cpi_raw[['Date', 'cpi_yoy']].copy()
        else: macro_df = pd.merge(macro_df, cpi_raw[['Date', 'cpi_yoy']], on='Date', how='outer')

    # 3. 원자재 및 환율
    print("📡 원자재 및 환율 데이터 수집 중...")
    corn = yf.download('ZC=F', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    corn.columns = ['Date', 'Corn_Price']
    wheat = yf.download('ZW=F', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    wheat.columns = ['Date', 'Wheat_Price']
    usd_krw = safe_fetch_fdr('USD/KRW', FETCH_START_DATE, END_DATE, 'USD_KRW')
    tiger_cp = safe_fetch_fdr('227560', FETCH_START_DATE, END_DATE, 'ETF_Close')

    # 4. 시계열 병합
    full_stocks = full_stocks.sort_values(['Stock_Name', 'Date'])
    merged = pd.merge(full_stocks, usd_krw, on='Date', how='left')
    merged = pd.merge(merged, tiger_cp, on='Date', how='left')
    
    for df in [corn, wheat]:
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize()
    merged = pd.merge(merged, corn, on='Date', how='left')
    merged = pd.merge(merged, wheat, on='Date', how='left')
    
    if not macro_df.empty:
        macro_df = macro_df.sort_values('Date')
        merged = pd.merge_asof(merged.sort_values('Date'), macro_df, on='Date', direction='backward')

    # 5. 재무 데이터 통합
    print("📡 재무제표 통합 및 전방 채우기(ffill) 중...")
    funda_files = [f'fundamental_{y}_Q{q}.csv' for y in [2022, 2023, 2024, 2025] for q in [1, 2, 3, 4] if not (y == 2025 and q == 4)]
    funda_list = [pd.read_csv(f) for f in funda_files if os.path.exists(f)]
    
    funda_cols = ['revenue_growth', 'operating_margin', 'ebitda', 'revenue']
    if funda_list:
        df_funda = pd.concat(funda_list)
        df_funda = df_funda[['end_date', '종목명'] + funda_cols].rename(columns={'end_date': 'Date', '종목명': 'Stock_Name'})
        df_funda['Date'] = pd.to_datetime(df_funda['Date']).dt.normalize()
        merged = pd.merge(merged, df_funda, on=['Date', 'Stock_Name'], how='left')
    else:
        for c in funda_cols: merged[c] = np.nan

    # 결측치 보정
    merged = merged.sort_values(['Stock_Name', 'Date'])
    fill_cols = ['USD_KRW', 'ETF_Close', 'Corn_Price', 'Wheat_Price', 'csi_sentiment', 'cpi_yoy'] + funda_cols
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill()
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산
# ============================================================
def calculate_staples_metrics(group):
    group = group.sort_values('Date')
    
    # 1. 원화 환산 원가 모멘텀
    group['raw_cost'] = (group['Corn_Price'] + group['Wheat_Price']) * group['USD_KRW']
    group['cost_momentum'] = group['raw_cost'].pct_change(60)
    
    # 2. 실질 성장률 및 에비타 마진
    group['real_revenue_growth'] = group['revenue_growth'] - group['cpi_yoy']
    group['ebitda_margin'] = group['ebitda'] / (group['revenue'] + 1e-9)
    
    # 3. 마진 방어력 (Correlation)
    window = 120
    op_margin_std = group['operating_margin'].rolling(window).std()
    cost_mom_std = group['cost_momentum'].rolling(window).std()
    raw_corr = group['operating_margin'].rolling(window).corr(group['cost_momentum'])
    group['margin_defense'] = raw_corr.where((op_margin_std > 1e-10) & (cost_mom_std > 1e-10), 0.0)
    group['margin_defense'] = group['margin_defense'].replace([np.inf, -np.inf], 0.0).fillna(0).clip(-1, 1)
    
    # 4. 산업 내 상대 강도 Z-score
    rel_price = group['Close'] / (group['ETF_Close'] + 1e-9)
    group['z_score'] = (rel_price - rel_price.rolling(window).mean()) / (rel_price.rolling(window).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_cons_staples_data()
    
    if not df_raw.empty:
        print("🚀 생활소비재 섹터 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_staples_metrics)
        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # [최종 컬럼 구성 - CLI 제외]
        final_cols = [
            'Date', 'Ticker', 'Stock_Name', 'Close', 
            'real_revenue_growth', 'ebitda_margin', 'margin_defense', 
            'csi_sentiment', 'z_score'
        ]
        df_final = df_final[final_cols].fillna(0)

        df_final.to_csv('cons_staples_processed.csv', index=False, encoding='utf-8-sig')
        print("-" * 30)
        print("✅ 생활소비재 전처리 완료 (CLI 제외): cons_staples_processed.csv")
        print(df_final.head(5))