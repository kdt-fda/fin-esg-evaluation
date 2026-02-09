import FinanceDataReader as fdr
import pandas_datareader.data as web
import yfinance as yf
import pandas as pd

start_date = '2023-01-01'
end_date = '2025-12-31'

# 종목 데이터 불러오기 및 통합
df_2023 = pd.read_csv('stock_data_2023.csv')
df_2024 = pd.read_csv('stock_data_2024.csv')
df_2025 = pd.read_csv('stock_data_2025.csv')
df_merged = pd.concat([df_2023, df_2024, df_2025])

stma = ['고려아연', 'POSCO홀딩스', '현대제철', '풍산', '세아베스틸지주',
        '영풍', '동원시스템즈', '율촌화학', '아세아', '세아제강지주']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(stma)]

# 철강/소재 추가 파생 지표
# 1. 경기 : 글로벌 제조업 PMI -> 수요
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
ipman = ipman.rename(columns={'DATE': 'Date'})
ipman['Date'] = pd.to_datetime(ipman['Date'])
# ipman.to_csv('IPMAN.csv', index=False)

# 투자 환경 (PMI lag) 지표 생성
# 철강/소재 업황의 선행성을 고려하여 1, 3개월 시차 적용
ipman['IPMAN_lag1'] = ipman['IPMAN'].shift(1) # 1개월 전 경기 지표
ipman['IPMAN_lag3'] = ipman['IPMAN'].shift(3) # 3개월 전 경기 지표

# 데이터 통합 (종목 데이터와 병합)
# 월간 PMI 데이터를 일간 주가 데이터에 매칭할 때 ffill()로 빈 날짜를 채워줍니다.
df_merged = pd.merge(df_merged, ipman, on='Date', how='left')
df_merged[['IPMAN', 'IPMAN_lag1', 'IPMAN_lag3']] = df_merged[['IPMAN', 'IPMAN_lag1', 'IPMAN_lag3']].ffill()

# 2. 가격 : 철강 PPI(WPS101) -> 단가
ppi_met = web.DataReader('WPS101', 'fred', start_date, end_date)
ppi_met = ppi_met.reset_index()
ppi_met = ppi_met.rename(columns={'DATE': 'Date'})
ppi_met = ppi_met.rename(columns={'WPS101': 'PPI_met'})
ppi_met['Date'] = pd.to_datetime(ppi_met['Date'])
# ppi_met.to_csv('PPI_met.csv', index=False)

# 3. 가격 : 비철금속 가격 (구리) -> 실적
copper = yf.Ticker('HG=F')
copper = copper.history(start=start_date, end=end_date)
copper = copper['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
copper['Date'] = pd.to_datetime(copper['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
copper['Date'] = copper['Date'].dt.normalize()
# copper.to_csv('HG=F.csv', index=False)

# 4. 민감도 : 원자재 베타 -> 반응 (구리 선물 / 유가 / 철강 PPI)
# 비철금속 - 구리 선물 (HG=F) 이미 가져옴

# 에너지 - 유가(WTI) (CL=F)
wti = yf.Ticker('CL=F')
wti = wti.history(start=start_date, end=end_date)
wti = wti['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
wti['Date'] = pd.to_datetime(wti['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
wti['Date'] = wti['Date'].dt.normalize()
# wti.to_csv('CL=F.csv', index=False)

# 철강제품 - 철강 PPI 이미 가져옴 PPI_met

# 데이터 통합 (종목 데이터와 병합, 순차적 통합)
# PPI, 구리, WTI 데이터를 일간 주가 데이터에 매칭할 때 ffill()로 빈 날짜를 채워줍니다.
df_merged = pd.merge(df_merged, ppi_met[['Date', 'PPI_met']], on='Date', how='left')
df_merged = pd.merge(df_merged, copper[['Date', 'Close']], on='Date', how='left', suffixes=('', '_copper'))
df_merged = pd.merge(df_merged, wti[['Date', 'Close']], on='Date', how='left', suffixes=('', '_wti'))

df_merged[['PPI_met', 'Close_copper', 'Close_wti']] = df_merged[['PPI_met', 'Close_copper', 'Close_wti']].ffill()

# 수익률 계산 (종목 주가 및 원자재 데이터)
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_copper'] = df_merged['Close_copper'].pct_change()
df_merged['ret_wti'] = df_merged['Close_wti'].pct_change()
df_merged['ret_ppi'] = df_merged['PPI_met'].pct_change()

# 60일 Rolling 원자재 베타 산출 함수
def get_rolling_beta(df, asset_ret_col):
    rolling_cov = df['ret_stock'].rolling(60).cov(df[asset_ret_col])
    rolling_var = df[asset_ret_col].rolling(60).var()
    return rolling_cov / rolling_var

# 각 지표별 베타 생성
df_merged['beta_copper'] = get_rolling_beta(df_merged, 'ret_copper')
df_merged['beta_wti'] = get_rolling_beta(df_merged, 'ret_wti')
df_merged['beta_ppi'] = get_rolling_beta(df_merged, 'ret_ppi')

# 5. 중국 : 중국 제조업 PMI(Calxin/공식) -> 정책 (PMI lag)
# 가져옴 PMI_CN

# 6. 상대 : KRX 철강 지수 -> 상대 강도 (Z-score)
# KODEX 철강 ETF
KODEXstl = fdr.DataReader('117680', start_date, end_date)
KODEXstl = KODEXstl['Close']
KODEXstl = KODEXstl.reset_index()
# KODEXstl.to_csv('KODEXstl.csv', index=False)

# 데이터 통합 (df_merged + KODEXstl)
df_merged = pd.merge(df_merged, KODEXstl, on='Date', how='left', suffixes=('', '_kodexstl'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_kodexstl']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']