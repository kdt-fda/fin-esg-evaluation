import FinanceDataReader as fdr
import pandas_datareader.data as web
import pandas as pd

start_date = '2023-01-01'
end_date = '2025-12-31'

# 종목 데이터 불러오기 및 통합
df_2023 = pd.read_csv('stock_data_2023.csv')
df_2024 = pd.read_csv('stock_data_2024.csv')
df_2025 = pd.read_csv('stock_data_2025.csv')
df_merged = pd.concat([df_2023, df_2024, df_2025])

cons = ['삼성물산', '현대건설', '삼성E&A', '한전기술', 'KCC',
        '대우건설', 'DL이앤씨', 'GS건설', '한일시멘트', 'DL']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(cons)]

# 건설 추가 파생 지표
# 1. 금리 : 국고채 10년물 금리 -> 자금 비용 (금리 변화)
kr10yt = fdr.DataReader('INVESTING:KR10YT=RR', start_date, end_date)
kr10yt = kr10yt['Close']
kr10yt = kr10yt.reset_index()
kr10yt.columns = ['Date', 'Close']
# kr10yt.to_csv('KR10YT.csv', index=False)

# 금리 변화율(Percentage Change) 계산
kr10yt['kr10yt_change'] = kr10yt['Close'].pct_change()

# 추가 지표: 금리 변화의 방향성 (Momentum)
kr10yt['kr10yt_diff'] = kr10yt['kr10yt_change'].diff()

# 2. 경기 : 건설업 PMI / 제조업 PMI -> 투자 수요 (PMI_lag)
# 건설업 PMI 업황실적BSI 대체
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
ipman = ipman.rename(columns={'DATE': 'Date'})
ipman['Date'] = pd.to_datetime(ipman['Date'])
# ipman.to_csv('IPMAN.csv', index=False)

# TODO: 건설업 업황실적 BSI (국내 데이터)
# 한국은행 경제통계시스템(ECOS) API 등을 통해 가져온 '건설업 업황실적' 데이터라고 가정합니다.

df_merged = pd.merge(ipman, bsi, left_index=True, right_on='Date', how='inner')

# 투자 수요 지표 (PMI_lag) 산출 로직
# 건설업은 수주 후 착공까지 시차가 발생하므로 1~3개월 Lag를 적용합니다.
df_merged['IPMAN_lag3'] = df_merged['IPMAN'].shift(3) # 3개월 선행 지표화
df_merged['BSI_lag1'] = df_merged['BSI'].shift(1) # 1개월 선행 지표화

# 최종 투자 수요 지표 생성 (제조업 경기와 건설 업황의 조화)
# 두 지표를 가중 평균하거나, 단순히 결합하여 새로운 '투자 수요' 변수를 만듭니다.
df_merged['Investment_Demand'] = (df_merged['IPMAN_lag3'] * 0.6) + (df_merged['BSI_lag1'] * 0.4)

# 3. 수주 : 해외건설 수주액 통계 -> 이벤트 (수주 더미/뉴스)
# TODO: 뉴스 기사로 처리?

# 4. 원가 : 시멘트/철강 PPI -> 마진 (원자재 변화)
# 가져옴 Cem_Ste_PPI

# 5. 상대 : 산업 Z-score
# TIGER 200 건설 ETF
TIGERcons = fdr.DataReader('139220', start_date, end_date)
TIGERcons = TIGERcons['Close']
TIGERcons = TIGERcons.reset_index()
# TIGERcons.to_csv('TIGERcons.csv', index=False)

# 데이터 통합 (종목 데이터 + TIGERcons)
df_merged = pd.merge(df_merged, TIGERcons, on='Date', how='left', suffixes=('', '_tigercons'))

# 상대 가격(Relative Price) 산출
df_merged['rel_price'] = df_merged['Close'] / df_merged['Close_tigercons']

# 120일 Rolling 평균 및 표준편차 산출
df_merged['rel_price_mean'] = df_merged['rel_price'].rolling(window=120).mean()
df_merged['rel_price_std'] = df_merged['rel_price'].rolling(window=120).std()

# 최종 산업 Z-score 계산 (최근 120일 평균 대비 표준편차 산출)
df_merged['z_score'] = (df_merged['rel_price'] - df_merged['rel_price_mean']) / df_merged['rel_price_std']