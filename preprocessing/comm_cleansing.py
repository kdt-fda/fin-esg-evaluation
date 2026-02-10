import FinanceDataReader as fdr
import pandas as pd
import numpy as np
from pandas.tseries.offsets import Day

# ============================================================
# 1. 설정 및 기간 확장
# ============================================================
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
COMM_STOCKS = {
    'NAVER': '035420', '카카오': '035720', 'SK텔레콤': '017670', 
    '하이브': '352820', 'KT': '030200', '크래프톤': '259960', 
    'LG유플러스': '032640', '엔씨소프트': '036570', '넷마블': '251270', '제일기획': '030000'
}

FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - Day(250)).strftime('%Y-%m-%d')

def safe_fdr_fetch(ticker, start, end):
    """인덱스 이름 이슈를 방지하며 안전하게 데이터를 가져오는 헬퍼 함수"""
    df = fdr.DataReader(ticker, start, end)
    # 인덱스 이름을 'Date'로 강제 지정 후 컬럼으로 변환
    df.index.name = 'Date'
    return df.reset_index()

def fetch_all_data():
    """KeyError: 'Date'를 방지하는 데이터 수집 로직"""
    stock_list = []
    for name, ticker in COMM_STOCKS.items():
        print(f"📡 {name}({ticker}) 수집 중...")
        df = safe_fdr_fetch(ticker, FETCH_START_DATE, END_DATE)
        df = df[['Date', 'Close']].copy()
        df['Ticker'] = ticker
        df['Stock_Name'] = name
        stock_list.append(df)
    
    full_stocks = pd.concat(stock_list).sort_values(['Stock_Name', 'Date'])

    print("📡 외부 경제 지표 및 산업 ETF 수집 중...")
    # 외부 데이터 수집 시에도 safe_fdr_fetch 사용
    ndx = safe_fdr_fetch('^NDX', FETCH_START_DATE, END_DATE)[['Date', 'Close']]
    ndx.columns = ['Date', 'NDX_Close']
    
    us10yt = safe_fdr_fetch('US10YT', FETCH_START_DATE, END_DATE)[['Date', 'Close']]
    us10yt.columns = ['Date', 'US10YT_Close']

    tigercomm = safe_fdr_fetch('315270', FETCH_START_DATE, END_DATE)[['Date', 'Close']]
    tigercomm.columns = ['Date', 'TigerComm_Close']

    # 데이터 통합
    merged = pd.merge(full_stocks, ndx, on='Date', how='left')
    merged = pd.merge(merged, us10yt, on='Date', how='left')
    merged = pd.merge(merged, tigercomm, on='Date', how='left')
    
    return merged

# ============================================================
# 2. 지표 계산 함수
# ============================================================
def calculate_metrics(group):
    # NaN 방지를 위해 정렬 보장
    group = group.sort_values('Date')
    
    s_ret = group['Close'].pct_change()
    n_ret = group['NDX_Close'].shift(1).pct_change()
    i_ret = group['US10YT_Close'].pct_change()

    # 1. 나스닥 상관계수 (60일)
    group['corr_NDX'] = s_ret.rolling(60).corr(n_ret)

    # 2. 금리 베타 (60일)
    cov = s_ret.rolling(60).cov(i_ret)
    var = i_ret.rolling(60).var()
    group['interest_beta'] = cov / var

    # 3. 산업 Z-score (120일)
    rel_price = group['Close'] / group['TigerComm_Close']
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / rel_price.rolling(120).std()
    
    return group

# ============================================================
# 3. 실행 및 저장
# ============================================================
if __name__ == "__main__":
    # 1) 데이터 수집
    df_raw = fetch_all_data()

    # 2) 종목별 지표 계산
    print("🚀 지표 산출 중 (Lookback 적용)...")
    df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_metrics)

    # 3) 최종 필터링: 사용자 시작일 기준
    df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()

    # 4) 컬럼 정리 (Date, Ticker, Stock_Name, Close + 지표 3개)
    keep_cols = ['Date', 'Ticker', 'Stock_Name', 'Close', 'corr_NDX', 'interest_beta', 'z_score']
    df_final = df_final[keep_cols]

    # 5) 저장
    output_path = 'comm_processed.csv'
    df_final.to_csv(output_path, index=False, encoding='utf-8-sig')

    print("-" * 30)
    print(f"✅ 모든 오류 해결 및 리팩토링 완료: {output_path}")
    print(f"최종 데이터 컬럼: {df_final.columns.tolist()}")
    print(df_final.head(3))