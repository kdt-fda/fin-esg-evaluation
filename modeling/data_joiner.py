import pymysql
import os
import pandas as pd

class StockDataJoiner:
    def __init__(self):
        # 섹터 코드별 테이블 매핑
        self.sector_table_map = {
            'COMM': 'COMM_TB',
            'CONS': 'CONSTRUCTION_TB',
            'HI': 'HEAVY_IND_TB',
            'MAT': 'MATERIALS_TB',
            'ENG': 'ENER_CHEM_TB',
            'IT': 'IT_TB',
            'FIN': 'FINANCE_TB',
            'CS': 'CONS_STAPLES_TB',
            'CD': 'CONS_DISC_TB',
            'IND': 'INDUSTRIALS_TB',
            'HC': 'HEALTHCARE_TB'
        }

        # 분기별 종료일 매핑 (year와 결합하여 날짜 생성용)
        self.quarter_date_map = {
            1: '03-31', # 1분기
            2: '06-30', # 2분기
            3: '09-30', # 3분기
            4: '12-31'  # 4분기(사업보고서)
        }

    def _connect(self):
        host = os.environ.get('DB_HOST')
        port = int(os.environ.get('DB_PORT'))
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        db_name = os.getenv('DB_NAME')

        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name
        )

        return conn
    
    def get_sector_info(self, stock_name):
        """종목의 섹터 코드를 조회"""
        conn = self._connect()

        try:
            with conn.cursor() as cur:
                # KOSPI200_STOCKS_TB에서 종목명 일치 조회
                sql = "SELECT ticker, sector_code FROM KOSPI200_STOCKS_TB WHERE stock_name = %s"
                cur.execute(sql, (stock_name,))
                result = cur.fetchone()
                # result -> ('005930', 'IT')
                return result if result else (None, None)
        finally:
            conn.close()

    # ---------------------------------------------------------
    # 펀더멘털 전용 로딩 함수
    # ---------------------------------------------------------
    def load_fundamental(self, ticker, start_year=2022):
        """
        특정 종목의 펀더멘털 데이터를 가져옵니다. 
        2022년부터의 데이터를 가져와서 2023년 모델링의 '과거 이력'으로 사용합니다.
        """
        conn = self._connect()
        try:
            # 정렬 기준 year, quarter 순
            sql = f"""
                SELECT * FROM FUNDAMENTAL_TB 
                WHERE ticker = %s AND year >= %s
                ORDER BY year ASC, quarter ASC
            """
            df = pd.read_sql(sql, conn, params=[ticker, start_year])
            return df
        finally:
            conn.close()

    # ---------------------------------------------------------
    # 통합 데이터 로딩
    # ---------------------------------------------------------
    def load_full_features(self, stock_name, start_date=None, end_date=None):
        """
        [사용자 인터페이스] 종목명으로 모든 지표 데이터를 통합 로드
        """
        # 1. 종목명으로 티커와 섹터 조회
        ticker, sector_code = self.get_sector_info(stock_name)

        if not ticker:
            print(f"오류: '{stock_name}' 종목 정보를 DB에서 찾을 수 없습니다 (KOSPI200 종목 여부 확인)")
            return None
        
        sector_table = self.sector_table_map.get(sector_code)

        # 2. 통합 쿼리 (티커 기반)
        # SQL 쿼리 전략
        # (1) 거시경제, 공통 파생 지표는 trade_date로만 JOIN
        # (2) 뉴스, 섹터 파생 지표는 trade_date + ticker로 JOIN
        # (3) 펀더멘털은 연도, 분기별 자료이므로 따로 처리하여 병합
        query = f"""
                SELECT
                    S.*, N.score AS news_score, M.*, C.*, SEC.*
                FROM STOCK_TB S
                LEFT JOIN NEWS_TB N
                    ON S.trade_date = N.trade_date AND S.ticker = N.ticker
                LEFT JOIN MACROECONOMICS_TB M
                    ON S.trade_date = M.trade_date
                LEFT JOIN COMMON_TB C
                    ON S.trade_date = C.trade_date
                LEFT JOIN {sector_table} SEC
                    ON S.trade_date = SEC.trade_date AND S.ticker = SEC.ticker
                WHERE S.ticker = %s
                """
        
        params = [ticker]
        if start_date: query += " AND S.trade_date >= %s" ; params.append(start_date)
        if end_date: query += " AND S.trade_date <= %s" ; params.append(end_date)
        query += " ORDER BY S.trade_date ASC"

        conn = self._connect()
        try:
            df = pd.read_sql(query, conn, params=params)
            df = df.loc[:, ~df.columns.duplicated()] # 중복 컬럼 제거
            return df
        finally:
            conn.close()

    # ---------------------------------------------------------
    # 모델링 데이터셋
    # ---------------------------------------------------------
    def get_modeling_dataset(self, stock_name, start_date=None, end_date=None):
        """
        일별 지표와 펀더멘털을 시점 정합성에 맞게 병합하여
        최종 모델링용 데이터셋으로 반환
        """
        # 1. 일별 주가/지표 데이터 로드
        df_daily = self.load_full_features(stock_name, start_date=start_date, end_date=end_date)
        if df_daily is None or df_daily.empty: return None

        # 2. 펀더멘털 데이터 로드 (2022년부터 확보)
        ticker, _ = self.get_sector_info(stock_name)
        actual_start_year = int(start_date[:4]) - 1 if start_date else 2022
        df_funda = self.load_fundamental(ticker, start_year=actual_start_year)

        # 3. 데이터 병합 처리
        df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'])
        
        if not df_funda.empty:
            # year, quarter 기반 가상 종료일(fs_date) 생성
            def create_fs_date(row):
                q_month_day = self.quarter_date_map.get(int(row['quarter']))
                if q_month_day:
                    return pd.to_datetime(f"{int(row['year'])}-{q_month_day}")
                return None

            df_funda['fs_date'] = df_funda.apply(create_fs_date, axis=1)

            # 정렬 (merge_asof 필수 조건)
            df_daily = df_daily.sort_values('trade_date')
            df_funda = df_funda.sort_values('fs_date')

            # 4. 시계열 병합 (merge_asof)
            df_final = pd.merge_asof(
                df_daily, 
                df_funda, 
                left_on='trade_date', 
                right_on='fs_date', 
                direction='backward'
            )
            
            # 불필요한 컬럼 및 중복 컬럼 정리
            drop_cols = ['fs_date', 'year', 'quarter', 'price', 'ticker_y']
            df_final = df_final.drop(columns=[c for c in drop_cols if c in df_final.columns])

            if 'ticker_x' in df_final.columns:
                df_final = df_final.rename(columns={'ticker_x': 'ticker'})         
                
        else:
            df_final = df_daily

        # 5. 데이터 정제
        df_final = df_final.loc[:, ~df_final.columns.duplicated()]
        df_final = df_final.ffill()

        print(f"[{stock_name}] 모델링 데이터셋 생성 완료 -> {df_final.shape}")
        return df_final