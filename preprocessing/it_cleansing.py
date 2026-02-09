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

tech = ['삼성전자', 'SK하이닉스', 'SK스퀘어', '삼성SDI', '삼성전기',
        '한미반도체', 'LG전자', 'LG', '삼성에스디에스', '현대오토에버',
        '이수페타시스', 'LG씨엔에스', '포스코DX', 'LG디스플레이', 'LG이노텍']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(tech)]

# 정보기술 추가 파생 지표
# 1. 공통 : 나스닥 100 지수 (NDX) -> 글로벌 심리
ndx = fdr.DataReader('^NDX', start_date, end_date)
ndx = ndx['Close']
ndx = ndx.reset_index()
ndx.columns = ['Date', 'Close']
# ndx.to_csv('NDX.csv', index=False)

# 2. 공통 : 나스닥 상관계수/초과 수익 -> 동조성
soxx = yf.Ticker('SOXX')
soxx = soxx.history(start=start_date, end=end_date)
soxx = soxx['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
soxx['Date'] = pd.to_datetime(soxx['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
soxx['Date'] = soxx['Date'].dt.normalize()
# soxx.to_csv('SOXX.csv', index=False)

# 데이터 통합 (df_merged + soxx)
df_merged = pd.merge(df_merged, soxx[['Date', 'Close']], on='Date', how='left', suffixes=('', '_soxx'))
df_merged['Close_soxx'] = df_merged['Close_soxx'].ffill()

# 수익률 계산 및 시차 적용
# SOXX는 미국 시간이므로 한국 장에는 전날 종가가 영향을 미칩니다.
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_soxx'] = df_merged['Close_soxx'].shift(1).pct_change() # 1일 시차 적용

# 60일 Rolling 상관계수(corr_SOXX) 산출
df_merged['corr_SOXX'] = df_merged['ret_stock'].rolling(window=60).corr(df_merged['ret_soxx'])

# 3. 반도체 : 필라델피아 반도체 지수 (SOX) -> 반도체 흐름
sox = yf.Ticker('^SOX')
sox = sox.history(start=start_date, end=end_date)
sox = sox['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
sox['Date'] = pd.to_datetime(sox['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
sox['Date'] = sox['Date'].dt.normalize()
# sox.to_csv('SOX.csv', index=False)

# 4. 반도체 : 마이크론(MU) 주가 (DXI 대체) -> 사이클
mu = yf.Ticker('MU')
mu = mu.history(start=start_date, end=end_date)
mu = mu['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
mu['Date'] = pd.to_datetime(mu['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
mu['Date'] = mu['Date'].dt.normalize()
# mu.to_csv('MU.csv', index=False)

# 5. HW : 글로벌 IT 수요 (애플 주가 등) -> 부품 수요
aapl = yf.Ticker('AAPL')
aapl = aapl.history(start=start_date, end=end_date)
aapl = aapl['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
aapl['Date'] = pd.to_datetime(aapl['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
aapl['Date'] = aapl['Date'].dt.normalize()
# aapl.to_csv('AAPL.csv', index=False)

# 6. 서비스 : OECD 경기선행지수 (CLI) -> IT 투자 (MEI_CLI)
# TODO: CLI 가져옴

# 7. 서비스 : 글로벌 제조업 PMI -> B2B 수요
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
ipman = ipman.rename(columns={'DATE': 'Date'})
ipman['Date'] = pd.to_datetime(ipman['Date'])
# ipman.to_csv('IPMAN.csv', index=False)

# 투자 환경 (PMI lag) 지표 생성
# 정보기술 업황의 선행성을 고려하여 1, 3개월 시차 적용
ipman['IPMAN_lag1'] = ipman['IPMAN'].shift(1) # 1개월 전 경기 지표
ipman['IPMAN_lag3'] = ipman['IPMAN'].shift(3) # 3개월 전 경기 지표

# 데이터 통합 (종목 데이터와 병합)
# 월간 PMI 데이터를 일간 주가 데이터에 매칭할 때 ffill()로 빈 날짜를 채워줍니다.
df_merged = pd.merge(df_merged, ipman, on='Date', how='left')
df_merged[['IPMAN', 'IPMAN_lag1', 'IPMAN_lag3']] = df_merged[['IPMAN', 'IPMAN_lag1', 'IPMAN_lag3']].ffill()

# 8. 상대 : IT Z-score -> 섹터 내 위치
# tiger 200 it etf
TIGERit = fdr.DataReader('139260', start_date, end_date)
TIGERit = TIGERit['Close']
TIGERit = TIGERit.reset_index()
TIGERit.columns = ['Date', 'Close']
# TIGERit.to_csv('TIGERit.csv', index=False)

# 데이터 통합 (df_merged + TIGERit)
df_merged = pd.merge(df_merged, TIGERit, on='Date', how='left', suffixes=('', '_tigerit'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_tigerit']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']