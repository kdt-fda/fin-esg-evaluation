import os
import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

# ============================================================
# [SECTION 1] 설정 및 기간 확장
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
# 60일 베타 등 지표 안정성을 위해 2021년부터 충분히 수집
FETCH_START_DATE = '2021-01-01'
START_YM = '202101'

ENCH_STOCKS = {
    'SK': '034730', 'LG화학': '051910', 'HD현대': '267250', 'SK이노베이션': '096770', 
    'S-oil': '010950', '한화': '000880', 'GS': '078930', '한화솔루션': '009830', 
    'SKC': '011790', '금호석유화학': '011780', '이수스페컬티케미컬': '457190', 
    '롯데케미칼': '011170', '한솔케미칼': '014680', 'OCI홀딩스': '010060', 
    '한국카본': '017960', '효성티앤씨': '298020', '코오롱인더': '120110', 
    '롯데정밀화학': '004000', 'SK케미칼': '285130', 'HS효성첨단소재': '298050',
    '태광산업': '003240', '대한유화': '006650', '후성': '093370', 
    'TKG휴켐스': '069260', '미원상사': '002840', '미원에스씨': '268280', '코스모화학': '005420'
}

# ============================================================
# [SECTION 2] Helper 함수 (타입 동기화 강화)
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
# [SECTION 3] 데이터 수집 및 통합 (Dtype 이슈 해결)
# ============================================================
def fetch_ener_chem_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 직접 수집
    stock_list = []
    for name, ticker in ENCH_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 공식 지표 수집
    print("📡 ECOS 에틸렌(30511101AA) 데이터 수집 중...")
    eth_df = ecos.fetch_data('404Y016', '30511101AA', START_YM, '202512')
    print("📡 ECOS 나프타(30412101AA) 데이터 수집 중...")
    nap_df = ecos.fetch_data('404Y016', '30412101AA', START_YM, '202512')
    print("📡 ECOS 제조업 생산지수(I11AC) 데이터 수집 중...")
    mfg_df = ecos.fetch_data('901Y032', 'I11AC', START_YM, '202512')

    # 매크로 가공
    macro_df = pd.DataFrame(columns=['Date'])
    if not eth_df.empty and not nap_df.empty:
        spread = pd.merge(eth_df.rename(columns={'Value':'E'}), nap_df.rename(columns={'Value':'N'}), on='Date', how='inner')
        spread['spread_momentum'] = (spread['E'] - spread['N']).pct_change(1)
        macro_df = spread[['Date', 'spread_momentum']]

    if not mfg_df.empty:
        mfg_df['mfg_lag3'] = mfg_df['Value'].shift(3)
        mfg_df['mfg_lag6'] = mfg_df['Value'].shift(6)
        if macro_df.empty: macro_df = mfg_df[['Date', 'mfg_lag3', 'mfg_lag6']]
        else: macro_df = pd.merge(macro_df, mfg_df[['Date', 'mfg_lag3', 'mfg_lag6']], on='Date', how='outer')

    # 3. yfinance 데이터 수집 및 즉각적인 타입 보정
    print("📡 글로벌 에너지(XLE) 데이터 수집 중...")
    xle_raw = yf.download('XLE', start=FETCH_START_DATE, end=END_DATE, progress=False)
    xle = xle_raw['Close'].reset_index()
    xle.columns = ['Date', 'XLE_Close']
    
    # [핵심] 타임존 제거 및 날짜 형식 표준화
    xle['Date'] = pd.to_datetime(xle['Date']).dt.tz_localize(None).dt.normalize()
    
    print("📡 KODEX 에너지화학(117460) 데이터 수집 중...")
    kodex_ench = safe_fetch_fdr('117460', FETCH_START_DATE, END_DATE, 'Ench_Close')

    # --------------------------------------------------------
    # [MergeError 방어] 모든 데이터프레임의 Date 타입을 다시 한 번 일치시킴
    # --------------------------------------------------------
    all_dfs = [full_stocks, xle, kodex_ench, macro_df]
    for i in range(len(all_dfs)):
        if all_dfs[i] is not None and not all_dfs[i].empty:
            # 모든 날짜 컬럼을 순수 Datetime 형식으로 변환
            all_dfs[i]['Date'] = pd.to_datetime(all_dfs[i]['Date']).dt.normalize()
            all_dfs[i] = all_dfs[i].sort_values('Date').reset_index(drop=True)

    full_stocks, xle, kodex_ench, macro_df = all_dfs

    # 4. 병합 (merge_asof)
    # 날짜 형식이 일치하므로 에러 없이 병합됨
    merged = pd.merge_asof(
        full_stocks, 
        xle, 
        on='Date', direction='backward', tolerance=pd.Timedelta('2D')
    )
    merged = pd.merge(merged, kodex_ench, on='Date', how='left')
    
    if not macro_df.empty:
        merged = pd.merge_asof(merged, macro_df, on='Date', direction='backward')

    # 5. 결측치 보정
    fill_cols = ['XLE_Close', 'Ench_Close', 'spread_momentum', 'mfg_lag3', 'mfg_lag6']
    merged = merged.sort_values(['Stock_Name', 'Date'])
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill()
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산
# ============================================================
def calculate_ener_chem_metrics(group):
    group = group.sort_values('Date')
    
    # 1. 오일 베타 (60일)
    s_ret = group['Close'].pct_change()
    x_ret = group['XLE_Close'].pct_change()
    group['oil_beta'] = s_ret.rolling(60, min_periods=40).cov(x_ret) / (x_ret.rolling(60, min_periods=40).var() + 1e-10)
    
    # 2. 산업 Z-score (120일)
    rel_price = group['Close'] / (group['Ench_Close'] + 1e-9)
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_ener_chem_data()
    
    if not df_raw.empty:
        print("🚀 에너지/화학 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_ener_chem_metrics)
        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # 저장
        df_final.to_csv('ener_chem_processed.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 전처리 완료: ener_chem_processed.csv (총 {len(df_final)}행)")
        print(df_final.head(5))