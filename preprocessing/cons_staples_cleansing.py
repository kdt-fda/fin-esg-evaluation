import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd

start_date = '2023-01-01'
end_date = '2025-12-31'

# 종목 데이터 불러오기 및 통합
df_2023 = pd.read_csv('stock_data_2023.csv')
df_2024 = pd.read_csv('stock_data_2024.csv')
df_2025 = pd.read_csv('stock_data_2025.csv')
df_merged = pd.concat([df_2023, df_2024, df_2025])

conp = ['한국전력', 'KT&G', '에이피알', '삼양식품', '아모레퍼시픽',
        'CJ', '오리온', 'LG생활건강', '한국가스공사', 'CJ제일제당',
        '롯데지주', '이마트', '농심', '동서', '아모레퍼시픽홀딩스',
        '코스맥스', 'BGF리테일', '동원산업', 'GS리테일', '한국콜마',
        '오뚜기', '오리온홀딩스', '롯데칠성', '지역난방공사', '하이트진로',
        '롯데웰푸드', '대상']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(conp)]

# 생활소비재 추가 파생 지표
# 소비 : 소비자심리지수 (CSI) -> 수요 (CSI lag)
# 가져옴 CSI TODO: lag 만들기

# 물가 : 소비자물가지수 (CPI) -> 원가/판가 (CPI 변화 / YoY)
# 가져옴 CPI TODO: 변화 만들기

# 원가 : 국제 농산물 가격 (옥수수, 소맥 등) -> 마진
corn = yf.Ticker('ZC=F')
corn = corn.history(start=start_date, end=end_date)
corn = corn.reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
corn['Date'] = pd.to_datetime(corn['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
corn['Date'] = corn['Date'].dt.normalize()
# corn.to_csv('ZC=F.csv', index=False)

wheat = fdr.DataReader('ZW=F', start_date, end_date)
wheat = wheat['Close']
wheat = wheat.reset_index()

# 날짜 형식 통일 (타임존 제거 및 날짜만 추출)
wheat['Date'] = pd.to_datetime(wheat['Date']).dt.tz_localize(None)

# 시간 정보를 제외하고 '연-월-일' 형식만 남기기
wheat['Date'] = wheat['Date'].dt.normalize()
# wheat.to_csv('ZW=F.csv', index=False)

# 마진 : 가격 전가력 -> 방어력 (재무제표/뉴스)
# TODO: 매출총이익/매출액 (GPM), 종목 매출 성장률 - CPI 상승률, 제품 가격 인상 변수 (인상 분기 1, 아니면 0)

# 방어 : KOSPI 대비 변동성 비율 -> 성격
# TODO: 종목 수익률 변동성(표준편차) / KOSPI 수익률 변동성(표준편차) 1과 비교

# 상대 : KRX 생활소비재 지수 -> 상대 강도 (Z-score)
# TIGER 200 생활소비재 etf
TIGERcp = fdr.DataReader('227560', start_date, end_date)
TIGERcp = TIGERcp['Close']
TIGERcp = TIGERcp.reset_index()
# TIGERcp.to_csv('TIGERcp.csv', index=False)