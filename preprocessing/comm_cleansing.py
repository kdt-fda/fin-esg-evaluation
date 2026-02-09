import FinanceDataReader as fdr
import pandas as pd

start_date = '2023-01-01'
end_date = '2025-12-31'

# 종목 데이터 불러오기 및 통합
df_2023 = pd.read_csv('stock_data_2023.csv')
df_2024 = pd.read_csv('stock_data_2024.csv')
df_2025 = pd.read_csv('stock_data_2025.csv')
df_merged = pd.concat([df_2023, df_2024, df_2025])

comm = ['NAVER', '카카오', 'SK텔레콤', '하이브', 'KT',
        '크래프톤', 'LG유플러스', '엔씨소프트', '넷마블', '제일기획']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(comm)]

# 커뮤니케이션서비스 추가 파생 지표
# 1. 성장 : 나스닥 100 지수 -> 글로벌 심리
ndx = fdr.DataReader('^NDX', start_date, end_date)
ndx = ndx['Close']
ndx = ndx.reset_index()
ndx.columns = ['Date', 'Close']
# ndx.to_csv('NDX.csv', index=False)

# 2. 성장 : 나스닥 상관계수 -> 동조성 (corr_NDX)
# 종목 데이터와 나스닥 데이터 결합 (Merge)
df_merged = pd.merge(df_merged, ndx, on='Date', how='left', suffixes=('', '_ndx'))

# 수익률(Return) 계산
# 나스닥은 한국 시간 기준 전날 종가를 반영하기 위해 shift(1) 적용
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_ndx'] = df_merged['Close_ndx'].shift(1).pct_change()

# 60일 Rolling Correlation 산출 (핵심 지표)
df_merged['corr_NDX'] = df_merged['ret_stock'].rolling(window=60).corr(df_merged['ret_ndx'])

# 3. 금리 : 미 10년물 국채 금리 -> 밸류에이션
us10yt = fdr.DataReader('US10YT', start_date, end_date)
us10yt = us10yt['Close']
us10yt = us10yt.reset_index()
us10yt.columns = ['Date', 'Close']
# us10yt.to_csv('US10YT.csv', index=False)

# 4. 민감도 : 금리 베타 -> 반응도
# 데이터 통합 (df_merged + us10yt)
df_merged = pd.merge(df_merged, us10yt, on='Date', how='left', suffixes=('', '_us10yt'))

# 금리 변화율 계산
df_merged['ret_us10yt'] = df_merged['Close_us10yt'].pct_change() # 금리 자체의 변화율

# 60일 Rolling 금리 베타 산출
# 공분산(Covariance) / 분산(Variance)
rolling_cov = df_merged['ret_stock'].rolling(window=60).cov(df_merged['ret_us10yt'])
rolling_var = df_merged['ret_us10yt'].rolling(window=60).var()

df_merged['interest_beta'] = rolling_cov / rolling_var

# 5. 이벤트 : 신작/신규 서비스 런칭일 -> 모멘텀
# TODO: 신작/신규 서비스 런칭일 해당 날짜 전후 1~2주를 1로, 나머지를 0으로 채우는 컬럼을 추가

# 6. 방어 : 배당 수익률(더미 변수) -> 통신주 특화
# TODO: 각 기업 IR 페이지에서 작년 배당금을 확인한 뒤 (배당금 / 현재 주가)를 계산한 컬럼

# 7. 상대 : 산업 Z-score -> 상대 강도
# TIGER200 커뮤니케이션서비스
tigercomm = fdr.DataReader('315270', start_date, end_date)
tigercomm = tigercomm['Close']
tigercomm = tigercomm.reset_index()
tigercomm.columns = ['Date', 'Close']
# tigercomm.to_csv('TIGERcomm.csv', index=False)

# 데이터 통합 (df_merged + tigercomm)
df_merged = pd.merge(df_merged, tigercomm, on='Date', how='left', suffixes=('', '_tigercomm'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_tigercomm']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']