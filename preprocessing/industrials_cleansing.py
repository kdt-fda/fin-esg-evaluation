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

ing = ['LG에너지솔루션', '한화에어로스페이스', '한화시스템', '포스코퓨처엠', 'HMM',
        'LS ELECTRIC', '현대글로비스', '한국항공우주', '포스코인터내셔널', 'LIG넥스원',
        '대한항공', 'LS', '대한전선', '엘앤에프', '에코프로머티',
        '에스원', '팬오션', '한전KPS', 'CJ대한통운', 'SK아이이테크놀로지']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(ing)]

# 산업재 추가 파생 지표
# 경기 : 글로벌 제조업 PMI -> 투자 환경 (글로벌 PMI lag)
# 제조업 산업 생산 지수
ipman = web.DataReader('IPMAN', 'fred', start_date, end_date)
ipman = ipman.reset_index()
# ipman.to_csv('IPMAN.csv', index=False)

# 물류 : 상하이컨테이너운임지수(SCFI) -> 물류 수요 (운임 지수 변화)
# 가져옴 SCFI

# 물류 : BDI (발틱운임지수) -> 원자재 교역 (물동량 lag)
# 가져옴 BDI

# 정책 : 국방/인프라 예산 공시 -> 방산, 인프라 (정책 더미)
# TODO: 정부 부처/뉴스?

# 수주 : 대형 공급계약 공시 빈도 -> 사이클 (수주 더미/뉴스 빈도)
# TODO: KIND / 뉴스?

# 변동성 : KOSPI 대비 변동성 비율 -> 민감도 (VolRatio)
# TODO: 종목별 종가, KOSPI200 지수는 있음

# 상대 : 산업 Z-score -> 상대 강도
# TIGER 200 산업재 etf
TIGERig = fdr.DataReader('227550', start_date, end_date)
TIGERig = TIGERig['Close']
TIGERig = TIGERig.reset_index()
# TIGERig.to_csv('TIGERig.csv', index=False)