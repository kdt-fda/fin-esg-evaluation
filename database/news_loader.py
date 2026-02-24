import pandas as pd
import pymysql
import os

def _connect():
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

def upload_news_score_csv(file_path):
    conn = _connect()
    
    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        
        # 2. DB에서 종목명-티커 매핑 정보 가져오기
        # (KOSPI200_STOCKS_TB에 이미 데이터가 들어있어야 합니다)
        cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB")
        mapping_rows = cur.fetchall()
        name_to_ticker = {row['stock_name']: row['ticker'] for row in mapping_rows}
        
        if not name_to_ticker:
            print("오류: KOSPI200_STOCKS_TB에 데이터가 없습니다. 종목 업데이트를 먼저 진행하세요.")
            return

        # 3. CSV 로드
        df = pd.read_csv(file_path)
        
        # 4. 데이터 전처리
        # - ticker 매핑
        # - 날짜 형식 변환
        # - 컬럼명 매칭 (company -> stock_name, date -> trade_date)
        df['ticker'] = df['company'].map(name_to_ticker)
        
        # 매핑되지 않은(KOSPI200에 없는) 종목 제거
        missing_count = df['ticker'].isna().sum()
        if missing_count > 0:
            missing_names = df[df['ticker'].isna()]['company'].unique()
            print(f"주의: {missing_count}개의 행이 KOSPI200 종목 리스트에 없어 제외됩니다. (예: {missing_names[:5]})")
            df = df.dropna(subset=['ticker'])

        # 삽입할 데이터 리스트 생성
        # NEWS_TB: trade_date, ticker, stock_name, score
        upload_data = []
        for _, row in df.iterrows():
            upload_data.append((
                row['date'],       # trade_date
                row['ticker'],     # ticker
                row['company'],    # stock_name
                row['score']       # score
            ))

        # 5. DB 삽입 (UPSERT)
        sql = """
            INSERT INTO NEWS_TB (trade_date, ticker, stock_name, score)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            score = VALUES(score);
        """
        
        cur.executemany(sql, upload_data)
        conn.commit()
        print(f"성공: {len(upload_data)}개의 뉴스 점수 데이터가 NEWS_TB에 저장되었습니다.")

    except Exception as e:
        print(f"오류 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    # 파일명이 다를 경우 수정하세요
    upload_news_score_csv('news_score.csv')