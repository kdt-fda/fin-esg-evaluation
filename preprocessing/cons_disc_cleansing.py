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

# 지표 안정성을 위해 수집 시작일을 넉넉하게 확장 (24개월 전)
FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - DateOffset(months=24)).strftime('%Y-%m-%d')
ECOS_START_YM = (pd.to_datetime(USER_START_DATE) - DateOffset(months=30)).strftime('%Y%m')

DISC_STOCKS = {
    '현대차': '005380', '기아': '000270', '현대모비스': '012330', '한국타이어앤테크놀로지': '161390',
    '한진칼': '180640', '코웨이': '021240', '한온시스템': '018880', '영원무역': '111770',
    '강원랜드': '035250', '신세계': '004170', 'HL만도': '204320', '영원무역홀딩스': '009970',
    'F&F': '383220', '롯데쇼핑': '023530', '미스토홀딩스': '004710', '한국앤컴퍼니': '000240',
    '에스엘': '005030', '현대백화점': '069960', '현대위아': '011210', '호텔신라': '008770',
    '파라다이스': '034230', '금호타이어': '073240', 'DN오토모티브': '007340', '더블유게임즈': '192080',
    '한샘': '024900', '세방전지': '004490', 'GKL': '114090'
}

# ============================================================
# [SECTION 2] Helper 함수 (ECOS 공식 코드 반영)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"
    def __init__(self):
        self.api_key = os.getenv("ECOS_API_KEY")

    def fetch_data(self, stat_code, item_code, start, end):
        # 주기 M(월) 고정하여 요청
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/500/{stat_code}/M/{start}/{end}/{item_code}"
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
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        return df[['Date', val_col]].rename(columns={val_col: col_name})
    except: return pd.DataFrame()

# ============================================================
# [SECTION 3] 데이터 수집 및 병합 (공식 지표 결합)
# ============================================================
def fetch_cons_disc_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가 수집
    stock_list = []
    for name, ticker in DISC_STOCKS.items():
        print(f"📡 {name}({ticker}) 주가 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        if not df.empty:
            df['Ticker'], df['Stock_Name'] = ticker, name
            stock_list.append(df)
    full_stocks = pd.concat(stock_list).reset_index(drop=True)

    # 2. ECOS 공식 지표 수집 (이미지 기반 코드 수정)
    print("📡 ECOS 소비자심리지수 및 경기선행지수 수집 중...")
    # 소비자심리지수: 511Y002 -> FME [이미지 확인 완료]
    csi_raw = ecos.fetch_data('511Y002', 'FME', ECOS_START_YM, '202512')
    # 선행종합지수(2020=100): 901Y067 -> I16A [이미지 확인 완료]
    cli_raw = ecos.fetch_data('901Y067', 'I16A', ECOS_START_YM, '202512')
    
    macro_df = pd.DataFrame(columns=['Date'])
    if not csi_raw.empty:
        csi_raw['csi_sentiment'] = csi_raw['Value'].shift(2) # 2개월 선행성
        macro_df = csi_raw[['Date', 'csi_sentiment']].copy()
    if not cli_raw.empty:
        cli_raw['cli_lag'] = cli_raw['Value'].shift(3) # 3개월 선행성
        if macro_df.empty:
            macro_df = cli_raw[['Date', 'cli_lag']].copy()
        else:
            macro_df = pd.merge(macro_df, cli_raw[['Date', 'cli_lag']], on='Date', how='outer')

    # 3. 기타 매크로 지표
    real_dpi = fdr.DataReader('FRED:DSPIC96', FETCH_START_DATE, END_DATE).reset_index()
    real_dpi.columns = ['Date', 'Real_DPI']
    real_dpi['Date'] = pd.to_datetime(real_dpi['Date']).dt.normalize()
    
    dgs10 = fdr.DataReader('FRED:DGS10', FETCH_START_DATE, END_DATE).reset_index()
    dgs10.columns = ['Date', 'US10Y']
    dgs10['Date'] = pd.to_datetime(dgs10['Date']).dt.normalize()
    
    tiger_cd = safe_fetch_fdr('139290', FETCH_START_DATE, END_DATE, 'ETF_Close')

    # 4. 시계열 병합 (merge_asof 핵심 적용)
    # 기업별 묶음 정렬을 위해 Stock_Name과 Date로 정렬
    full_stocks = full_stocks.sort_values(['Stock_Name', 'Date'])
    merged = pd.merge(full_stocks, tiger_cd, on='Date', how='left')
    merged = pd.merge(merged, real_dpi, on='Date', how='left')
    merged = pd.merge(merged, dgs10, on='Date', how='left')
    
    if not macro_df.empty:
        macro_df = macro_df.sort_values('Date')
        merged = pd.merge_asof(merged.sort_values('Date'), macro_df, on='Date', direction='backward')

    # 결측치 보정 (기업별 ffill)
    fill_cols = ['ETF_Close', 'Real_DPI', 'US10Y', 'csi_sentiment', 'cli_lag']
    for col in fill_cols:
        if col not in merged.columns: merged[col] = np.nan

    merged = merged.sort_values(['Stock_Name', 'Date'])
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill()
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].bfill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산
# ============================================================
def calculate_disc_metrics(group):
    group = group.sort_values('Date')
    
    # 1. 소득 모멘텀
    group['purchasing_power_mom'] = group['Real_DPI'].pct_change(60)
    
    # 2. 금리 민감도 (Beta) - 안정성 확보
    ir_ret = group['US10Y'].shift(1).pct_change()
    ir_var = ir_ret.rolling(60).var()
    group['durables_ir_beta'] = (group['Close'].pct_change().rolling(60).cov(ir_ret) / (ir_var + 1e-9)).clip(-10, 10)
    
    # 3. Z-score (상대 강도)
    rel_price = group['Close'] / (group['ETF_Close'] + 1e-9)
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / (rel_price.rolling(120).std() + 1e-9)
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_cons_disc_data()
    
    if not df_raw.empty:
        print("🚀 경기소비재 섹터 파생 지표 산출 중...")
        df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_disc_metrics)
        
        # [정렬 규칙] 기업별 묶음 -> 시간순
        df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
        
        # 분석 대상일 필터링
        df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
        
        # 검증 통계 로그
        print("-" * 30)
        print(f"📊 CSI(FME) 평균: {df_final['csi_sentiment'].mean():.2f}")
        print(f"📊 CLI(I16A) 평균: {df_final['cli_lag'].mean():.2f}")
        
        # 최종 컬럼 순서 고정
        final_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'purchasing_power_mom', 'durables_ir_beta', 'csi_sentiment', 'cli_lag', 'z_score']
        df_final = df_final[final_cols].fillna(0)

        df_final.to_csv('cons_disc_processed.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 전처리 완료: cons_disc_processed.csv")
        print(df_final.head(10))