import FinanceDataReader as fdr
import pandas as pd

start_date = '2023-01-01'
end_date = '2025-12-31'

# 종목 데이터 불러오기 및 통합
df_2023 = pd.read_csv('stock_data_2023.csv')
df_2024 = pd.read_csv('stock_data_2024.csv')
df_2025 = pd.read_csv('stock_data_2025.csv')
df_merged = pd.concat([df_2023, df_2024, df_2025])

heal = ['삼성바이오로직스', '셀트리온', '삼성에피스홀딩스', 'SK바이오팜', '유한양행',
        '한미약품', 'SK바이오사이언스', '한미사이언스', '한올바이오파마', '녹십자',
        '대웅제약', '대웅', '종근당', '에스디바이오센서', '녹십자홀딩스']

df_merged["Date"] = pd.to_datetime(df_merged["Date"], format="%Y.%m.%d")

df_merged = df_merged[df_merged["Stock_Name"].isin(heal)]

# 헬스케어 추가 파생 지표
# 이벤트 : 임상/허가 일정 (이벤트 거리) -> 모멘텀
# TODO: 뉴스 기사? 주요 일정 전후 주가 변동성

# 뉴스 : 핵심 키워드 뉴스 빈도 -> 기대 변화
# TODO: 뉴스 기사? 뉴스량 급증 시 투심 변화

# R&D : R&D 투자 비중 -> 성장 잠재력
# TODO: 연구개발비 총액/매출액 * 100%

# 기대 : PBR 기반 밸류 Z-score -> 과열 판단
# TODO: 일별 PBR

# 변동성 : KOSPI 대비 변동성 비율 -> 성격
# TODO: 종목별 일종가, KOSPI200 지수 있음

# 정책 : 바이오 육성/규제 정책 뉴스 -> 규제
# TODO: 뉴스 기사? 정책적 영향

# 상대 : 산업 Z-score -> 상대 강도
# TIGER 200 헬스케어 etf
TIGERhc = fdr.DataReader('227540', start_date, end_date)
TIGERhc = TIGERhc['Close']
TIGERhc = TIGERhc.reset_index()
# TIGERhc.to_csv('TIGERhc.csv', index=False)