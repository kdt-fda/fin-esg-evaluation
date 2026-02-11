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
# 지표 안정성(120일 Z-score 등)을 위해 2021년부터 충분히 수집
FETCH_START_DATE = '2021-01-01'
START_YM = '202101'

HEAVY_STOCKS = {
    '두산에너빌리티': '034020', 'HD현대중공업': '329180', '한화오션': '042660',
    'HD현대일렉트릭': '267260', 'HD한국조선해양': '009540', '삼성중공업': '010140',
    '현대로템': '064350', '효성중공업': '298040', '두산': '000150',
    'HD현대마린솔루션': '443060', '두산로보틱스': '454910', '두산밥캣': '241560',
    '한화엔진': '082740', '산일전기': '062040', '현대엘리베이터': '017800',
    'HD현대마린엔진': '071670', '씨에스윈드': '112610'
}

# ============================================================
# [SECTION 2] Helper 함수 (Dtype 강제 고정 및 로그 유지)
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
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        df = df[['Date', val_col]].rename(columns={val_col: col_name})
        return df.sort_values('Date').drop_duplicates('Date')
    except: return pd.DataFrame(columns=['Date', col_name])

# ============================================================
# [SECTION 3] 데이터 수집 및 통합 (MergeError & 결측치 방어)
# ============================================================
def fetch_heavy_ind_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 수집
    stock_list = []
    for name, ticker in HEAVY_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 제조업 생산지수(I11AC) 수집
    print("📡 ECOS 제조업 생산지수(I11AC) 데이터 수집 중...")
    mfg_df = ecos.fetch_data('901Y032', 'I11AC', START_YM, '202512')
    mfg_df = mfg_df.rename(columns={'Value': 'mfg_idx'})

    # 3. 환율 및 거시 지표 수집
    print("📡 원/달러 환율(USDKRW=X) 수집 중...")
    usd_krw_raw = yf.download('USDKRW=X', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    usd_krw_raw.columns = ['Date', 'USD_KRW']
    
    print("📡 에너지 지표(WTI 선물) 수집 중...")
    wti_raw = yf.download('CL=F', start=FETCH_START_DATE, end=END_DATE, progress=False)['Close'].reset_index()
    wti_raw.columns = ['Date', 'WTI_Close']
    
    print("📡 KODEX 기계장비(102960) 데이터 수집 중...")
    mach_etf = safe_fetch_fdr('102960', FETCH_START_DATE, END_DATE, 'Mach_Close')

    # 병합 전 타입 동기화 (MergeError 방지)
    def force_sync(df):
        df = df.copy()
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.normalize().astype('datetime64[ns]')
        return df.sort_values('Date').reset_index(drop=True)

    full_stocks = force_sync(full_stocks)
    usd_krw, wti, mach_etf = force_sync(usd_krw_raw), force_sync(wti_raw), force_sync(mach_etf)
    mfg_df = force_sync(mfg_df)

    # 4. 시계열 병합 (기존 흐름 유지)
    merged = pd.merge_asof(full_stocks, usd_krw, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge_asof(merged, wti, on='Date', direction='backward', tolerance=pd.Timedelta('2D'))
    merged = pd.merge(merged, mach_etf, on='Date', how='left')
    merged = pd.merge_asof(merged, mfg_df, on='Date', direction='backward')

    # 5. [핵심] 병합 후 종목별 결측치 보정 (중간 비어있는 구간 방지)
    fill_cols = ['USD_KRW', 'WTI_Close', 'Mach_Close', 'mfg_idx']
    merged = merged.sort_values(['Stock_Name', 'Date'])
    # groupby ffill/bfill로 공휴일 등으로 인한 중간 NaN을 완벽히 메움
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill().bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산 (else 0 및 0 채우기 없음)
# ============================================================
def calculate_heavy_metrics(group):
    group = group.sort_values('Date')
    s_ret = group['Close'].pct_change()
    
    # 1. 환율 민감도 (FX Beta) - 60일 윈도우
    if 'USD_KRW' in group.columns:
        u_ret = group['USD_KRW'].pct_change()
        # 공분산/분산으로 베타 산출 (1.0보다 크면 환율 상승 시 주가 더 크게 상승)
        group['fx_beta'] = group['Close'].pct_change(20).rolling(60).cov(group['USD_KRW'].pct_change(20)) / \
                           (group['USD_KRW'].pct_change(20).rolling(60).var() + 1e-10)
    
    # 2. [수정] 제조업 지수 모멘텀 (실제 시계열 기준)
    if 'mfg_idx' in group.columns:
        # 행 기준 3이 아니라, 영업일 기준 60일(약 3개월) 전의 지수와 비교해야 함
        group['mfg_momentum'] = group['mfg_idx'].pct_change(60) 
        # mfg_lag3는 이미 60일 shift로 잘 구현되어 있음
        group['mfg_lag3'] = group['mfg_idx'].shift(60)
    
    # 3. 에너지 발주 모멘텀 (WTI 60일 이동평균의 변화율)
    if 'WTI_Close' in group.columns:
        wti_ma = group['WTI_Close'].rolling(60, min_periods=20).mean()
        group['energy_momentum'] = wti_ma.pct_change(20)
    
    # 4. 산업 내 상대 강도 Z-score (120일)
    if 'Mach_Close' in group.columns:
        rel_price = group['Close'] / (group['Mach_Close'] + 1e-9)
        # 안정적인 흐름을 위해 120일 윈도우 사용
        group['z_score'] = (rel_price - rel_price.rolling(120, min_periods=30).mean()) / \
                           (rel_price.rolling(120, min_periods=30).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_heavy_ind_data()
    
    if not df_raw.empty:
        print("🚀 중공업 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_heavy_metrics)
        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        
        # 분석 대상 기간으로 필터링
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # 최종 컬럼 구성 (인위적인 0 채우기 절대 없음)
        final_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'fx_beta', 'mfg_momentum', 'mfg_lag3', 'energy_momentum', 'z_score']
        actual_cols = [c for c in final_cols if c in df_final.columns]
        df_final = df_final[actual_cols]

        df_final.to_csv('heavy_ind_processed.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 흐름 유지 및 NaN 방어 완료: heavy_ind_processed.csv (총 {len(df_final)}행)")
        print(df_final.head(10))