import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import DateOffset

# ============================================================
# [SECTION 1] 설정 및 기간 확장
# ============================================================
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'

FIN_STOCKS = {
    'KB금융': '105560', '신한지주': '055550', '삼성생명': '032830', '하나금융지주': '086790', 
    '미래에셋증권': '006800', '우리금융지주': '316140', '삼성화재': '000810', '메리츠금융지주': '138040', 
    '기업은행': '024110', '카카오뱅크': '323410', '한국금융지주': '071050', '키움증권': '039490', 
    'DB손해보험': '005830', 'NH투자증권': '005940', '카카오페이': '377300', '삼성증권': '016360', 
    '삼성카드': '029780', 'BNK금융지주': '138930', 'JB금융지주': '175330', '한화생명': '088350', 
    '현대해상': '001450', 'iM금융지주': '139130'
}

# 120일 Z-score 및 60일 베타 산출을 위해 시작일 확장
FETCH_START_DATE = (pd.to_datetime(USER_START_DATE) - DateOffset(months=10)).strftime('%Y-%m-%d')

def safe_fetch_fdr(ticker, start, end, col_name='Close'):
    """KeyError 방지 및 Date 컬럼 보장을 위한 안전 수집 함수"""
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
# [SECTION 2] 데이터 수집 및 통합
# ============================================================
def fetch_finance_data():
    # 1. 개별 종목 주가
    stock_list = []
    for name, ticker in FIN_STOCKS.items():
        print(f"📡 {name}({ticker}) 데이터 수집 중...")
        df = safe_fetch_fdr(ticker, FETCH_START_DATE, END_DATE, 'Close')
        df['Ticker'], df['Stock_Name'] = ticker, name
        stock_list.append(df)
    full_stocks = pd.concat(stock_list)

    # 2. 금융 매크로 지표 수집
    print("📡 금융 매크로 지표(금리, VIX, XLF) 수집 중...")
    
    # 미국 장단기 금리차 (10Y-2Y)
    t10y2y = safe_fetch_fdr('T10Y2Y', FETCH_START_DATE, END_DATE, 'T10Y2Y')
    
    # 국고채 10년물 (금리 베타용)
    kr10y = safe_fetch_fdr('INVESTING:KR10YT=RR', FETCH_START_DATE, END_DATE, 'KR10Y')
    
    # 미국 금융 ETF (XLF) & VIX 지수
    xlf = safe_fetch_fdr('XLF', FETCH_START_DATE, END_DATE, 'XLF_Close')
    vix = safe_fetch_fdr('^VIX', FETCH_START_DATE, END_DATE, 'VIX_Close')
    
    # 상대 강도용 TIGER 200 금융 ETF
    tiger_fin = safe_fetch_fdr('139270', FETCH_START_DATE, END_DATE, 'Fin_ETF_Close')

    # 3. 데이터 병합
    full_stocks = full_stocks.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
    merged = pd.merge(full_stocks, t10y2y, on='Date', how='left')
    merged = pd.merge(merged, kr10y, on='Date', how='left')
    merged = pd.merge(merged, xlf, on='Date', how='left')
    merged = pd.merge(merged, vix, on='Date', how='left')
    merged = pd.merge(merged, tiger_fin, on='Date', how='left')
    
    # 결측치 보정 (기업별 ffill)
    merged = merged.sort_values(['Stock_Name', 'Date'])
    fill_cols = ['T10Y2Y', 'KR10Y', 'XLF_Close', 'VIX_Close', 'Fin_ETF_Close']
    merged[fill_cols] = merged.groupby('Stock_Name')[fill_cols].ffill()
        
    return merged

# ============================================================
# [SECTION 3] 파생 지표 계산 (수정 버전)
# ============================================================
def calculate_finance_metrics(group):
    group = group.sort_values('Date')
    
    # 주가 수익률
    s_ret = group['Close'].pct_change()
    
    # 1. 개선된 금리 민감도 (Interest Sensitivity)
    # pct_change() 대신 금리 변동분(diff)을 사용하여 베타 폭주 방지
    # 금리 1%p 변동 시 주가 수익률이 몇 % 변하는지 산출
    k_diff = group['KR10Y'].diff() 
    
    # 60일 공분산 / 분산 계산 (수치 안정화)
    rolling_cov = s_ret.rolling(60).cov(k_diff)
    rolling_var = k_diff.rolling(60).var()
    
    # 베타 산출 및 이상치 클리핑 (너무 크거나 작은 값 방지)
    # 보통 금리 민감도는 -5 ~ 5 사이에서 형성되는 것이 안정적입니다.
    group['interest_beta'] = (rolling_cov / rolling_var).clip(-10, 10)
    
    # 2. 시장 공포 민감도 (VIX Correlation)
    v_ret = group['VIX_Close'].pct_change()
    group['vix_corr'] = s_ret.rolling(60).corr(v_ret).fillna(0)
    
    # 3. 글로벌 금융 동조화 (XLF Beta)
    x_ret = group['XLF_Close'].shift(1).pct_change()
    group['global_fin_beta'] = (s_ret.rolling(60).cov(x_ret) / x_ret.rolling(60).var()).clip(-5, 5)
    
    # 4. 산업 내 상대 강도 Z-score (120일)
    rel_price = group['Close'] / group['Fin_ETF_Close']
    group['z_score'] = (rel_price - rel_price.rolling(120).mean()) / rel_price.rolling(120).std()
    
    return group

# ============================================================
# [SECTION 4] 실행 및 최종 저장 (기업별 묶음 정렬)
# ============================================================
if __name__ == "__main__":
    df_raw = fetch_finance_data()
    
    print("🚀 금융 섹터 파생 지표 산출 중...")
    df_processed = df_raw.groupby('Stock_Name', group_keys=False).apply(calculate_finance_metrics)
    
    # [정렬 규칙] 기업별 묶음 -> 시간순
    df_processed = df_processed.sort_values(['Stock_Name', 'Date']).reset_index(drop=True)
    
    # 시작일 필터링
    df_final = df_processed[df_processed['Date'] >= USER_START_DATE].copy()
    
    # [컬럼 규칙] 일관된 순서 유지 (Date, Ticker, Name, Close, 지표 4개)
    final_cols = [
        'Date', 'Ticker', 'Stock_Name', 'Close', 
        'interest_beta', 'vix_corr', 'global_fin_beta', 'z_score'
    ]
    df_final = df_final[final_cols].fillna(0)

    # 최종 저장
    output_filename = 'finance_processed.csv'
    df_final.to_csv(output_filename, index=False, encoding='utf-8-sig')

    print("-" * 30)
    print(f"✅ 기업별 묶음 정렬 및 금융 전처리 완료: {output_filename}")
    print(df_final.head(10))