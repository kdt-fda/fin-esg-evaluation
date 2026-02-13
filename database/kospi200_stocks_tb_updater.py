import pymysql
from pykrx import stock
from datetime import datetime

def update_kospi200_stocks_table():
    # DB 연결
    conn = pymysql.connect(
        host='52.79.234.231',
        port=3302,
        user='root',
        password='team2',
        database='STOCK_DB',
        charset='utf8mb4',
    )

    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)

        # 현재 날짜 기준 KOSPI200 구성 종목 ticker 가져오기
        today = datetime.now().strftime('%Y%m%d')
        tickers = stock.get_index_portfolio_deposit_file('1028', today)

        # 모든 종목의 상태를 일단 비활성(False)으로 업데이트
        # 이번 리스트에 포함된 종목만 아래에서 True로 바뀜
        cur.execute('UPDATE KOSPI200_STOCKS_TB SET is_active = FALSE;')

        # 최신 종목 데이터 준비 : ticker 이용 종목명 매칭
        # [(ticker, stock_name)...] 리스트 생성
        data = []
        for ticker in tickers:
            stock_name = stock.get_market_ticker_name(ticker)
            data.append((ticker, stock_name, True))

        if data:
            # UPSERT : 있으면 업데이트 (이름/상태), 없으면 신규 삽입
            sql = """
                INSERT INTO KOSPI200_STOCKS_TB (ticker, stock_name, is_active)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                stock_name = VALUES(stock_name),
                is_active = VALUES(is_active);
                """
            cur.executemany(sql, data)
            conn.commit()
            print(f'[{datetime.now()}] KOSPI200 종목 동기화 완료 ({len(data)}건)')

        # 커밋 직후 동일한 커서로 다시 조회해보기
        cur.execute("SELECT COUNT(*) AS total FROM KOSPI200_STOCKS_TB;")
        count = cur.fetchone()['total'] # DictCursor 기준
        print(f"현재 테이블 내 총 데이터 수: {count}개")

        if count > 0:
            cur.execute("SELECT * FROM KOSPI200_STOCKS_TB LIMIT 5;")
            print("상위 5개 데이터 샘플:", cur.fetchall())

    except Exception as e:
        print(f'오류 발생: {e}')
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 실행 부분
# ---------------------------------------------------------
if __name__ == '__main__':
    update_kospi200_stocks_table()