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

fin = ['KB금융', '신한지주', '삼성생명', '하나금융지주', '미래에셋증권',
        '우리금융지주', '삼성화재', '메리츠금융지주', '기업은행', '카카오뱅크',
        '한국금융지주', '키움증권', 'DB손해보험', 'NH투자증권', '카카오페이',
        '삼성증권', '삼성카드', 'BNK금융지주', 'JB금융지주', '한화생명',
        '현대해상', 'iM금융지주']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(fin)]

# 금융 추가 파생 지표
# 1. 금리 : 10Y-2Y 스프레드 -> 이자마진
t10y2y = web.DataReader('T10Y2Y', 'fred', start_date, end_date)
t10y2y = t10y2y.reset_index()
t10y2y = t10y2y.rename(columns={'DATE': 'Date'})
t10y2y['Date'] = pd.to_datetime(t10y2y['Date'])
t10y2y = t10y2y.ffill()
# t10y2y.to_csv('T10Y2Y.csv', index=False)

# 2. 금리 : 스프레드 변화 -> 전일 대비 변화량
t10y2y['T10Y2Y_diff'] = t10y2y['T10Y2Y'].diff()
# t10y2y.to_csv('T10Y2Y_diff.csv', index=False)

# 3. 정책 : 한국/미국 기준금리 -> 정책 방향
# ecos 데이터 불러오기
ecos = pd.read_csv('ecos.csv')
ecos = ecos.rename(columns={'date': 'Date'}) # 'Date'로 통일
ecos['Date'] = pd.to_datetime(ecos['Date'])

# fred 데이터 불러오기
fred = pd.read_csv('fred.csv')
fred = fred.rename(columns={'date': 'Date'}) # 'Date'로 통일
fred['Date'] = pd.to_datetime(fred['Date'])

# 한국 기준금리
kr_rate = ecos[['Date', 'base_rate']]
kr_rate = kr_rate.rename(columns={'base_rate': 'kr_rate'})
kr_rate = kr_rate.ffill()

# 미국 기준금리
us_rate = fred[['Date', 'us_policy_rate']]
us_rate = us_rate.rename(columns={'us_policy_rate': 'us_rate'})
us_rate = us_rate.ffill()

# 데이터 통합 (한국 기준금리 + 미국 기준금리)
policy = pd.merge(kr_rate, us_rate, on='Date', how='inner')

# 한-미 금리 스프레드 (정책 차이)
policy['rate_spread'] = policy['us_rate'] - policy['kr_rate']

# 정책 기조 (Stance) - 최근 3개월간 금리 변화량
# 금리가 인상 기조인지 동결/인하 기조인지 수치화
policy['kr_policy_change'] = policy['kr_rate'].diff(60)
policy['us_policy_change'] = policy['us_rate'].diff(60)

# 국고채 3년물
ktb3y = ecos[['Date', 'ktb3y']]
ktb3y = ktb3y.ffill()

# 국고채 10년물
ktb10y = ecos[['Date', 'ktb10y']]
ktb10y = ktb10y.ffill()

# 데이터 통합 (기준금리 + 국고채 3, 10년물) 순차적으로 통합
policy = pd.merge(policy, ktb3y, on='Date', how='inner')
policy = pd.merge(policy, ktb10y, on='Date', how='inner')

# 장단기 금리차 (Term Spread) - 은행 NIM 선행 지표
# 국고채 10년물(kr10y)과 3년물(kr3y)
policy['term_spread'] = policy['ktb10y'] - policy['ktb3y']

# 4. 민감도 : 금융 ETF -> 금리 베타
xlf = yf.Ticker('XLF')
xlf = xlf.history(start=start_date, end=end_date)
xlf = xlf['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
xlf['Date'] = pd.to_datetime(xlf['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
xlf['Date'] = xlf['Date'].dt.normalize()
# xlf.to_csv('XLF.csv', index=False)

# 데이터 통합 (종목 데이터 + 국고채 10년물 + XLF)
df_merged = pd.merge(df_merged, ktb10y, on='Date', how='inner')
df_merged = pd.merge(df_merged, xlf, on='Date', how='inner', suffixes=('', '_xlf'))

# 수익률(Return) 계산
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_ktb10y'] = df_merged['ktb10y'].pct_change() # 금리 변화율
df_merged['ret_xlf'] = df_merged['Close_xlf'].pct_change()    # 금융 섹터 수익률

# 60일 Rolling 금리 베타 산출 (종목 vs 국고채 10년물)
# 금리가 1% 변할 때 주가가 변하는 민감도
rolling_cov_bond = df_merged['ret_stock'].rolling(window=60).cov(df_merged['ret_ktb10y'])
rolling_var_bond = df_merged['ret_ktb10y'].rolling(window=60).var()
df_merged['interest_beta'] = rolling_cov_bond / rolling_var_bond

# 60일 Rolling 섹터 베타 산출 (종목 vs 금융 ETF)
# 금융 섹터 전체 움직임 대비 해당 종목의 탄력성
rolling_cov_etf = df_merged['ret_stock'].rolling(window=60).cov(df_merged['ret_xlf'])
rolling_var_etf = df_merged['ret_xlf'].rolling(window=60).var()
df_merged['sector_beta'] = rolling_cov_etf / rolling_var_etf

# 5. 시장 : VIX 지수(공포지수) -> 증권 수익
vix = yf.Ticker('^VIX')
vix = vix.history(start=start_date, end=end_date)
vix = vix['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
vix['Date'] = pd.to_datetime(vix['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
vix['Date'] = vix['Date'].dt.normalize()
# vix.to_csv('VIX.csv', index=False)

# 6. 방어 : KOSPI 대비 상대 변동성 -> 성격 구분 (하락장에서의 방어력 및 저베타 특성 분석)
kospi200 = fdr.DataReader('KS200', start=start_date, end=end_date)
kospi200 = kospi200['Close']
kospi200 = kospi200.reset_index()

# 시장 변동성 (수익률 표준편차) 산출
# 일간 수익률 계산
kospi200['ret_mkt'] = kospi200['Close'].pct_change()

# 20일 Rolling 표준편차 (한 달간의 시장 흔들림)
# 연율화(Annualized)를 위해 np.sqrt(252)를 곱하기도 하지만, 
# 모델 피처로는 원형 데이터를 그대로 쓰거나 로그 변환을 주로 합니다.
kospi200['mkt_vol'] = kospi200['ret_mkt'].rolling(window=20).std()

# 7. 상대 : KRX 금융 지수 -> 산업 Z-score
# TIGER200 금융 ETF
TIGERfin = fdr.DataReader('139270', start_date, end_date)
TIGERfin = TIGERfin['Close']
TIGERfin = TIGERfin.reset_index()
# TIGERfin.to_csv('TIGERfin.csv', index=False)

# 데이터 통합 (df_merged + TIGERfin)
df_merged = pd.merge(df_merged, TIGERfin, on='Date', how='left', suffixes=('', '_tigerfin'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_tigerfin']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']