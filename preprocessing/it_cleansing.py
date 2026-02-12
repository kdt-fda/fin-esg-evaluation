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

TECH_STOCKS = {
    '삼성전자': '005930', 'SK하이닉스': '000660', 'SK스퀘어': '402340', 
    '삼성SDI': '006400', '삼성전기': '009150', '한미반도체': '042700', 
    'LG전자': '066570', 'LG': '003550', '삼성에스디에스': '018260', 
    '현대오토에버': '307950', '이수페타시스': '007660', 'LG씨엔에스': '064400',
    '포스코DX': '022100', 'LG디스플레이': '034220', 'LG이노텍': '011070'
}

FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - DateOffset(months=10)).strftime('%Y-%m-%d')
ECOS_START_YM = (pd.to_datetime(USER_START_DATE) - DateOffset(months=12)).strftime('%Y%m')

# ============================================================
# [SECTION 2] ECOS Client 및 데이터 수집 함수
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
            df['Date'] = pd.to_datetime(df['TIME'], format='%Y%m')
            df['Value'] = pd.to_numeric(df['DATA_VALUE'])
            return df[['Date', 'Value']].sort_values('Date')
        except:
            return pd.DataFrame()

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    try:
        df = fdr.DataReader(ticker, start, end)
        df.index.name = 'Date'
        df = df.reset_index()
        df.columns = [c.capitalize() if c.lower() == 'date' else c for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date'])
        val_col = 'Close' if 'Close' in df.columns else df.columns[1]
        return df[['Date', val_col]].rename(columns={val_col: col_name})
    except:
        return pd.DataFrame(columns=['Date', col_name])

# ============================================================
# [SECTION 3] 데이터 통합 및 지표 정확도 보정
# ============================================================
def fetch_it_data():
    ecos = EcosClient()
    
    # 1. 개별 종목 주가
    stock_list = []
    for name, ticker in TECH_STOCKS.items():
        print(f"📡 {name}({ticker}) 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        df['Ticker'], df['Stock_Name'] = ticker, name
        stock_list.append(df)
    full_stocks = pd.concat(stock_list)

    # 2. 글로벌 동적 지표 수집
    soxx = safe_fetch_fdr('SOXX', FETCH_START_DATE, END_DATE, 'SOXX_Close')
    aapl = safe_fetch_fdr('AAPL', FETCH_START_DATE, END_DATE, 'AAPL_Close')
    xli = safe_fetch_fdr('XLI', FETCH_START_DATE, END_DATE, 'XLI_Close') # 제조업 경기
    tiger_it = safe_fetch_fdr('139260', FETCH_START_DATE, END_DATE, 'IT_ETF_Close')

    # 3. OECD CLI 수집 및 모멘텀 사전 계산 (0 이슈 해결 핵심)
    print("📡 IT 경기 선행지표(CLI) 분석 중...")
    cli_df = ecos.fetch_data('901Y068', 'I16D', ECOS_START_YM, '202512')
    
    if not cli_df.empty:
        # 월간 데이터 상태에서 미리 변화율을 구해야 일간으로 확장해도 0이 안 나옴
        cli_df['cli_momentum'] = cli_df['Value'].pct_change(1)
    else:
        # [Fallback] CLI가 없을 경우 나스닥100(QQQ)의 월간 모멘텀으로 대체하여 '의미 있는 숫자' 확보
        print("⚠️ CLI 데이터 부재로 글로벌 기술주 모멘텀(QQQ)으로 대체 산출합니다.")
        qqq = fdr.DataReader('QQQ', FETCH_START_DATE, END_DATE).resample('MS').last()
        qqq['cli_momentum'] = qqq['Close'].pct_change(1)
        cli_df = qqq[['cli_momentum']].reset_index().rename(columns={'index': 'Date'})

    # 4. 데이터 병합
    full_stocks = full_stocks.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
    merged = pd.merge(full_stocks, soxx, on='Date', how='left')
    merged = pd.merge(merged, aapl, on='Date', how='left')
    merged = pd.merge(merged, xli, on='Date', how='left')
    merged = pd.merge(merged, tiger_it, on='Date', how='left')
    
    # 타입 정규화 후 asof 병합
    merged['Date'] = pd.to_datetime(merged['Date'])
    cli_df['Date'] = pd.to_datetime(cli_df['Date'])
    merged = pd.merge_asof(merged.sort_values('Date'), cli_df[['Date', 'cli_momentum']], on='Date', direction='backward')

    # 결측치 보정 (기업별 ffill)
    merged = merged.sort_values(['Stock_Name', 'Date'])
    fill_cols = ['SOXX_Close', 'AAPL_Close', 'XLI_Close', 'IT_ETF_Close', 'cli_momentum']
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill()
        
    return merged

# ============================================================
# [SECTION 4] 파생 지표 계산
# ============================================================
def calculate_it_metrics(group):
    group = group.sort_values('Date')
    s_ret = group['Close'].pct_change()
    
    # 1. 반도체 동조성 (SOXX 상관계수)
    soxx_ret = group['SOXX_Close'].shift(1).pct_change()
    group['soxx_corr'] = s_ret.rolling(60).corr(soxx_ret)
    
    # 2. 글로벌 IT 수요 모멘텀 (애플 60일 변화율)
    group['apple_momentum'] = group['AAPL_Close'].pct_change(60)
    
    # 3. 글로벌 제조업 경기 선행 모멘텀 (XLI 60일 변화율)
    group['mfg_cycle_momentum'] = group['XLI_Close'].pct_change(60)
    
    # 4. 산업 내 상대 강도 Z-score (120일)
    rel_price = group['Close'] / group['IT_ETF_Close']
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / rel_price.rolling(120).std()
    
    return group

# ============================================================
# [SECTION 5] 실행 및 최종 저장
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_it_data()
    
    print("🚀 정보기술 섹터 파생 지표 산출 중...")
    df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_it_metrics)
    
    # [정렬 규칙] 기업별 묶어서 시간순
    df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
    
    df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
    
    # 최종 컬럼 순서
    final_cols = [
        'Date', 'Ticker', 'Stock_Name', 'Close', 
        'soxx_corr', 'apple_momentum', 'mfg_cycle_momentum', 'z_score'
    ]
    df_final = df_final[final_cols].fillna(0)

    df_final.to_csv('it_processed.csv', index=False, encoding='utf-8-sig')

    print("-" * 30)
    print("✅ 데이터 정확도 보정 및 전처리 완료: it_processed.csv")
    print(df_final.head(10))