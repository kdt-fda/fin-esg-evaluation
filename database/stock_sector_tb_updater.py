import pymysql
from pykrx import stock
from datetime import datetime
import time

def update_stock_sector_table():
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

        # [참조 무결성 체크] 부모 테이블(KOSPI200_STOCKS_TB)에 있는 ticker만 가져오기
        cur.execute('SELECT ticker FROM KOSPI200_STOCKS_TB;')
        parent_tickers = {row['ticker'] for row in cur.fetchall()}

        # [참조 무결성 체크] 부모 테이블(SECTOR_TB)에 있는 sector_code만 가져오기
        cur.execute('SELECT sector_code FROM SECTOR_TB')
        parent_sectors = {row['sector_code'] for row in cur.fetchall()}

        mapping_data = []
        print('KRX로부터 섹터별 종목 리스트 수집 중...')

        for eng_code, krx_code in sector_map.items():
            # 부모 테이블(SECTOR_TB)에 해당 영문 코드가 없으면 스킵 (FK 에러 방지)
            if eng_code not in parent_sectors:
                print(f"경고: SECTOR_TB에 '{eng_code}' 코드가 없어 스킵합니다.")
                continue

            # 지수 구성 종목 가져오기
            tickers_in_sector = stock.get_index_portfolio_deposit_file(krx_code, today)

            for ticker in tickers_in_sector:
                # 부모 테이블(KOSPI200_STOCKS_TB)에 ticker가 있는 경우만 매핑 추가 (FK 에러 방지)
                if ticker in parent_tickers:
                    mapping_data.append((ticker, eng_code))

            time.sleep(0.3)

        if mapping_data:
            # 기존 매핑 데이터 삭제 (항상 최신 상태 유지)
            cur.execute('DELETE FROM STOCK_SECTOR_TB')

            # 새로운 매핑 데이터 삽입
            sql = """
                INSERT INTO STOCK_SECTOR_TB (ticker, sector_code)
                VALUES (%s, %s)
                """
            cur.executemany(sql, mapping_data)
            conn.commit()
            print(f'성공: 총 {len(mapping_data)}건의 종목-섹터 매핑 완료')
        else:
            print('삽입할 매핑 데이터가 없습니다.')
    
    except Exception as e:
        conn.rollback()
        print(f'오류 발생으로 롤백: {e}')
    finally:
        conn.close()

# ---------------------------------------------------------
# 실행 부분
# ---------------------------------------------------------
if __name__ == '__main__':
    update_stock_sector_table()