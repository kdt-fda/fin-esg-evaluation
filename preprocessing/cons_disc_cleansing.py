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

cond = ['현대차', '기아', '현대모비스', '한국타이어앤테크놀로지', '한진칼',
        '코웨이', '한온시스템', '영원무역', '강원랜드', '신세계',
        'HL만도', '영원무역홀딩스', 'F&F', '롯데쇼핑', '미스토홀딩스',
        '한국앤컴퍼니', '에스엘', '현대백화점', '현대위아', '호텔신라',
        '파라다이스', '금호타이어', 'DN오토모티브', '더블유게임즈', '한샘',
        '세방전지', 'GKL']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(cond)]

# 경기소비재 추가 파생 지표
# 경기 : OECD 경기선행지수 (CLI) -> 경기 국면 (CLI lag)
# TODO: CLI 가져옴

# 심리 : 소비자심리지수 (CSI) -> 소비 심리 (CSI lag)
# 가져옴 CSI TODO: lag 만들기

# 소득 : 실질 가처분 소득 (Real DPI) -> 소비 여력 (실질소득 proxy)
real_dpi = fdr.DataReader('FRED:DSPIC96', start_date, end_date)
real_dpi = real_dpi.reset_index()
# real_dpi.to_csv('DSPIC96.csv', index=False)

# 금리 : 미 10년물 국채 금리 (DGS10) -> 내구재 (금리 베타) TODO: US10YT vs DGS10 <- 이게 공식 자료
dgs10 = fdr.DataReader('FRED:DGS10', start_date, end_date)
dgs10 = dgs10.reset_index()
# dgs10.to_csv('DGS10.csv', index=False)

# 관광 : 인천공항 입국자 수 통계 -> 면세, 레저 (입국자 lag)
# TODO: 뉴스 기사?

# 이벤트 : 소비 관련 규제 및 정책 뉴스 -> 정책 (규제 더미)
# TODO: 뉴스 기사?

# 상대 : 산업 Z-score -> 상대 강도
# TIGER 200 경기소비재 etf
TIGERcd = fdr.DataReader('139290', start_date, end_date)
TIGERcd = TIGERcd['Close']
TIGERcd = TIGERcd.reset_index()
# TIGERcd.to_csv('TIGERcd.csv', index=False)