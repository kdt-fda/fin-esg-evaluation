import pymysql
import pandas_market_calendars as mcal
from datetime import datetime, timedelta

def update_date_table():
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

        # DB에 가장 최근 저장된 날짜 확인
        cur.execute('SELECT MAX(trade_date) AS max_date FROM DATE_TB;')
        result = cur.fetchone()

        # 딕셔너리에서 max_date 키로 값을 가져옴
        last_date = result['max_date'] if result else None

        # 데이터가 하나도 없는 경우 -> initial
        # 2023-01-01부터 시작
        if last_date is None:
            start_date = '2023-01-01'
        else:
            # 데이터가 있는 경우
            start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')

        # 오늘 날짜 설정
        end_date = datetime.now().strftime('%Y-%m-%d')

        if start_date > end_date:
            print('이미 최신 상태입니다.')
            return
        
        # 한국거래소(XKRX) 달력 가져오기
        krx = mcal.get_calendar('XKRX')
        # 개장 시간 기준으로 실제 거래일 스케줄 추출
        schedule = krx.schedule(start_date=start_date, end_date=end_date)

        if not schedule.empty:
            # DB에 넣을 형식(YYYY-MM-DD)의 리스트 생성
            trade_date = [(day.strftime('%Y-%m-%d'),) for day in schedule.index]

            # 데이터 삽입 (중복 방지를 위해 INSERT IGNORE 사용)
            sql = 'INSERT IGNORE INTO DATE_TB (trade_date) VALUES (%s)'
            cur.executemany(sql, trade_date)
            conn.commit()
            print(f'성공: {len(trade_date)}개의 거래일이 추가되었습니다.')
        else:
            print('추가할 새로운 거래일이 없습니다.')

    except Exception as e:
        print(f'오류 발생: {e}')
        conn.rollback()
    finally:
        conn.close()

# ---------------------------------------------------------
# 실행 부분
# ---------------------------------------------------------
if __name__ == '__main__':
    update_date_table()