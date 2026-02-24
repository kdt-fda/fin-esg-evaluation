import pymysql
import os
from pykrx import stock
from dotenv import load_dotenv

load_dotenv()

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

def update_sector_table():
    conn = _connect()

    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)

        # 영문 코드 기반 섹터 리스트
        sector_data = [
            ('COMM', '커뮤니케이션서비스'),
            ('CONS', '건설'),
            ('HI', '중공업'),
            ('MAT', '철강/소재'),
            ('ENG', '에너지/화학'),
            ('IT', '정보기술'),
            ('FIN', '금융'),
            ('CS', '생활소비재'),
            ('CD', '경기소비재'),
            ('IND', '산업재'),
            ('HC', '헬스케어')
        ]

        # 기존 데이터 있다면 업데이트, 없으면 삽입
        sql = """
            INSERT INTO SECTOR_TB (sector_code, sector_name) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE sector_name = VALUES(sector_name);
            """
        cur.executemany(sql, sector_data)
        conn.commit()
        print(f'성공: {len(sector_data)}개의 영문 섹터 코드가 저장되었습니다.')

    except Exception as e:
        print(f'오류 발생: {e}')
    finally:
        conn.close()

# ---------------------------------------------------------
# 실행 부분
# ---------------------------------------------------------
if __name__ == '__main__':
    update_sector_table()