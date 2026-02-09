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

ench = ['SK', 'LG화학', 'HD현대', 'SK이노베이션', 'S-oil',
        '한화', 'GS', '한화솔루션', 'SKC', '금호석유화학',
        '이수스페컬티케미컬', '롯데케미칼', '한솔케미칼', 'OCI홀딩스', '한국카본',
        '효성티앤씨', '코오롱인더', '롯데정밀화학', 'SK케미칼', 'HS효성첨단소재',
        '태광산업', '대한유화', '후성', 'TKG휴켐스', '미원상사',
        '미원에스씨', '코스모화학']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(ench)]

# 화학 / 에너지 추가 파생 지표
# 1. 유가 : WTI 원유 선물 -> 유가 수익률
wti = yf.Ticker('CL=F')
wti = wti.history(start=start_date, end=end_date)
wti = wti['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
wti['Date'] = pd.to_datetime(wti['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
wti['Date'] = wti['Date'].dt.normalize()
# wti.to_csv('CL=F.csv', index=False)

# 유가 수익률(Return) 산출
# 일간 수익률 (Daily Return)
wti['wti_ret_1d'] = wti['Close'].pct_change()

# 주간 수익률 (5거래일 기준, 추세 파악용)
# 화학주는 유가의 단기 변동보다 1~2주의 방향성에 더 민감합니다.
wti['wti_ret_5d'] = wti['Close'].pct_change(periods=5)

# 유가 변동성 (Volatility) - 리스크 지표
# 유가가 급등락할 경우 화학사의 원가 관리 불확실성이 커집니다.
wti['wti_vol_20d'] = wti['wti_ret_1d'].rolling(window=20).std()

# 데이터 통합 (df_merged + wti)
df_merged = pd.merge(df_merged, wti[['Date', 'wti_ret_1', 'wti_ret_5', 'wti_vol_20']], on='Date', how='left')
df_merged = df_merged.ffill() # 공휴일 결측치 처리

# 2. 유가 : 두바이유 -> 유가 lag
dubai = web.DataReader('POILDUBUSDM', 'fred', start_date, end_date)
dubai = dubai.reset_index()
dubai = dubai.rename(columns={'DATE': 'Date', 'POILDUBUSDM': 'dubai'})
# dubai.to_csv('Dubai.csv', index=False)

# 발주 모멘텀 (유가 lag) 지표 생성
# 3개월(약 60영업일)과 6개월(약 120영업일) 시차를 적용하여 선행성 확보
dubai['dubai_lag60'] = dubai['dubai'].shift(3) # 3개월 전 추세
dubai['dubai_lag120'] = dubai['dubai'].shift(6) # 6개월 전 추세

# 데이터 통합 (df_merged + dubai)
df_merged = pd.merge(df_merged, dubai[['Date', 'dubai_lag60', 'dubai_lag120']], on='Date', how='left')
df_merged = df_merged.ffill() # 공휴일 결측치 처리

# 3. 민감도 : 에너지 ETF -> Oil beta
xle = yf.Ticker('XLE')
xle = xle.history(start=start_date, end=end_date)
xle = xle['Close'].reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
xle['Date'] = pd.to_datetime(xle['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
xle['Date'] = xle['Date'].dt.normalize()
# xle.to_csv('XLE.csv', index=False)

# 데이터 통합 (df_merged + xle)
df_merged = pd.merge(df_merged, xle[['Date', 'Close']], on='Date', how='left', suffixes=('', '_xle'))
df_merged['Close_xle'] = df_merged['Close_xle'].ffill()

# 수익률 계산 (종목 및 XLE)
# XLE는 미국 시장 데이터이므로 시차(shift)를 고려
df_merged['ret_stock'] = df_merged['Close'].pct_change()
df_merged['ret_xle'] = df_merged['Close_xle'].shift(1).pct_change() # 1일 시차 적용

# 60일 Rolling 오일 베타 산출
rolling_cov = df_merged['ret_stock'].rolling(window=60).cov(df_merged['ret_xle'])
rolling_var = df_merged['ret_xle'].rolling(window=60).var()
df_merged['oil_beta'] = rolling_cov / rolling_var

# 4. 마진 : 에틸렌-나프타 스프레드 -> 스프레드 proxy
# TODO: ECOS API 활용 직접 계산

# 5. 경기 : 글로벌 제조업 PMI -> PMI lag
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
ipman = ipman.rename(columns={'DATE': 'Date'})
ipman['Date'] = pd.to_datetime(ipman['Date'])
# ipman.to_csv('IPMAN.csv', index=False)

# 투자 환경 (PMI lag) 지표 생성
# 에너지/화학 업황의 선행성을 고려하여 3개월(1분기)과 6개월(2분기) 시차 적용
ipman['IPMAN_lag3'] = ipman['IPMAN'].shift(3) # 3개월 전 경기 지표
ipman['IPMAN_lag6'] = ipman['IPMAN'].shift(6) # 6개월 전 경기 지표

# 데이터 통합 (종목 데이터와 병합)
# 월간 PMI 데이터를 일간 주가 데이터에 매칭할 때 ffill()로 빈 날짜를 채워줍니다.
df_merged = pd.merge(df_merged, ipman, on='Date', how='left')
df_merged[['IPMAN', 'IPMAN_lag3', 'IPMAN_lag6']] = df_merged[['IPMAN', 'IPMAN_lag3', 'IPMAN_lag6']].ffill()

# 6. 상대 : KRX 에너지 화학지수 -> 산업 Z-score
# KODEX 에너지화학 ETF
KODEXench = fdr.DataReader('117460', start_date, end_date)
KODEXench = KODEXench['Close']
KODEXench = KODEXench.reset_index()
# KODEXench.to_csv('KODEXench.csv', index=False)

# 데이터 통합 (df_merged + KODEXmach)
df_merged = pd.merge(df_merged, KODEXench, on='Date', how='left', suffixes=('', '_kodexench'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_kodexench']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']