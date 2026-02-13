import pymysql
from pykrx import stock
from datetime import datetime
import time

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

    # 영문 코드와 KRX 지수 코드 매핑
    sector_map = {
        'COMM': '1150', 'CONS': '1151', 'HI': '1152', 'MAT': '1153',
        'ENG': '1154', 'IT': '1155', 'FIN': '1156', 'CS': '1157',
        'CD': '1158', 'IND': '1159', 'HC': '1160'
    }

    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        today = datetime.now().strftime('%Y%m%d')

        # 기존 종목 비활성화 (업데이트 전 초기화)
        cur.execute('UPDATE KOSPI200_STOCKS_TB SET is_active = FALSE;')

        # 섹터별로 돌면서 종목 정보 수집
        # [(ticker, stock_name, sector_code, is_active) ...]
        data = []

        print('섹터별 종목 데이터 수집 중...')

        for eng_code, krx_code in sector_map.items():
            # 해당 섹터 지수 구성 종목 가져오기
            tickers = stock.get_index_portfolio_deposit_file(krx_code, today)

            for ticker in tickers:
                stock_name = stock.get_market_ticker_name(ticker)
                data.append((ticker, stock_name, eng_code, True))

            time.sleep(0.3) # API 과부하 방지

        if data:
            # UPSERT : 있으면 업데이트 (이름/상태), 없으면 신규 삽입
            sql = """
                INSERT INTO KOSPI200_STOCKS_TB (ticker, stock_name, sector_code, is_active)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                stock_name = VALUES(stock_name),
                sector_code = VALUES(sector_code),
                is_active = VALUES(is_active);
                """
            cur.executemany(sql, data)
            conn.commit()
            print(f'[{datetime.now()}] KOSPI200 {len(data)}개 종목 정보 및 섹터 매핑 완료')
        else:
            print('수집된 종목 데이터가 없습니다.')

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