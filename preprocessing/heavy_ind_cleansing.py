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

heavy = ['두산에너빌리티', 'HD현대중공업', '한화오션', 'HD현대일렉트릭', 'HD한국조선해양',
        '삼성중공업', '현대로템', '효성중공업', '두산', 'HD현대마린솔루션',
        '두산로보틱스', '두산밥캣', '한화엔진', '산일전기', '현대엘리베이터',
        'HD현대마린엔진', '씨에스윈드']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(heavy)]

# 중공업 추가 파생 지표
# 1. 경기 : 글로벌 제조업 PMI -> 투자 환경 (PMI lag)
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
ipman = ipman.rename(columns={'DATE': 'Date'})
ipman['Date'] = pd.to_datetime(ipman['Date'])
# ipman.to_csv('IPMAN.csv', index=False)

# 투자 환경 (PMI lag) 지표 생성
# 중공업 업황의 선행성을 고려하여 3개월(1분기)과 6개월(2분기) 시차 적용
ipman['IPMAN_lag3'] = ipman['IPMAN'].shift(3) # 3개월 전 경기 지표
ipman['IPMAN_lag6'] = ipman['IPMAN'].shift(6) # 6개월 전 경기 지표

# 데이터 통합 (종목 데이터와 병합)
# 월간 PMI 데이터를 일간 주가 데이터에 매칭할 때 ffill()로 빈 날짜를 채워줍니다.
df_merged = pd.merge(df_merged, ipman, on='Date', how='left')
df_merged[['IPMAN', 'IPMAN_lag3', 'IPMAN_lag6']] = df_merged[['IPMAN', 'IPMAN_lag3', 'IPMAN_lag6']].ffill()

# 2. 수주 : 선박 수주 / 방산 수출 공시 -> 이벤트 (수주 더미/뉴스)
# TODO: 뉴스 기사?

# 3. 환율 : 원/달러 환율 -> 채산성 (FX수익률/베타)
# ECOS 데이터 로드 및 열 이름 정리
ecos = pd.read_csv('ecos.csv')
ecos = ecos.rename(columns={'date': 'Date'}) # 'Date'로 통일
ecos['Date'] = pd.to_datetime(ecos['Date'])

# 필요한 데이터만 추출 (날짜와 usdkrw 환율)
fx_data = ecos[['Date', 'usdkrw']].sort_values('Date')

# 데이터 통합 (df_merged + fx_data)
df_merged = pd.merge(df_merged, fx_data, on='Date', how='left')
df_merged['usdkrw'] = df_merged['usdkrw'].ffill() # 공휴일 등 결측치 처리

# 수익률 계산
# ret_fx = fx_momentum 채산성 모멘텀
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_fx'] = df_merged['usdkrw'].pct_change()

# FX 베타 (환율 민감도/채산성) 산출
# 최근 60일(1분기) 간의 상관관계를 회귀계수로 계산
rolling_cov = df_merged['ret_stock'].rolling(window=60).cov(df_merged['ret_fx'])
rolling_var = df_merged['ret_fx'].rolling(window=60).var()
df_merged['fx_beta'] = rolling_cov / rolling_var

# 4. 에너지 : WTI 가격 -> 발주 모멘텀 (유가 lag)
wti = yf.Ticker('CL=F')
wti = wti.history(start=start_date, end=end_date)
wti = wti['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
wti['Date'] = pd.to_datetime(wti['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
wti['Date'] = wti['Date'].dt.normalize()
# wti.to_csv('CL=F.csv', index=False)

# 발주 모멘텀 (유가 lag) 지표 생성
# 3개월(약 60영업일)과 6개월(약 120영업일) 시차를 적용하여 선행성 확보
wti['wti_lag60'] = wti['Close'].shift(60) # 3개월 전 추세
wti['wti_lag120'] = wti['Close'].shift(120) # 6개월 전 추세

# 데이터 통합 (df_merged + wti)
df_merged = pd.merge(df_merged, wti[['Date', 'wti_lag60', 'wti_lag120']], on='Date', how='left')
df_merged = df_merged.ffill() # 결측치 처리

# 5. 정책 : 국방 예산 / 에너지 정책 -> 테마 (정부 발표나 뉴스로 정책 더미)
# TODO: 뉴스 기사?

# 6. 상대 : KRX 기계장비 / 조선 지수 -> 상대 강도 (Z-score)
# KODEX 기계장비 ETF
KODEXmach = fdr.DataReader('102960', start_date, end_date)
KODEXmach = KODEXmach['Close']
KODEXmach = KODEXmach.reset_index()
KODEXmach.columns = ['Date', 'Close']
# KODEXmach.to_csv('KODEXmach.csv', index=False)

# 데이터 통합 (df_merged + KODEXmach)
df_merged = pd.merge(df_merged, KODEXmach, on='Date', how='left', suffixes=('', '_kodexmach'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_kodexmach']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']