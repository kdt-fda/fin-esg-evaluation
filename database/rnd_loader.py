import pandas as pd
import pymysql
import os
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# DB 설정
DB_CONFIG = {
    'host': '52.79.234.231', 
    'port': 3302, 
    'user': 'root',
    'password': 'team2', 
    'database': 'STOCK_DB', 
    'charset': 'utf8mb4'
}

def load_rnd_to_db():
    # 파일 경로 (data 폴더 내 RND.csv)
    file_path = 'data/RND.csv'
    
    if not os.path.exists(file_path):
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
        return

    # 1. CSV 로드
    df = pd.read_csv(file_path)
    
    # 2. 전처리 (CSV 컬럼 -> DB 컬럼 매칭)
    # CSV 헤더: 기업종목코드, 종목명, end_date, year, quarter, rnd_expense
    # DB 컬럼: ticker, year, quarter, rnd_expense
    
    df_to_db = df[['기업종목코드', 'year', 'quarter', 'rnd_expense']].copy()
    
    # 종목코드를 6자리 문자열로 변환 (예: 137310 -> '137310')
    df_to_db['기업종목코드'] = df_to_db['기업종목코드'].astype(str).str.zfill(6)
    
    # NaN 처리
    df_to_db = df_to_db.replace({np.nan: None})

    # 3. DB 연결 및 적재
    conn = pymysql.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        
        # INSERT 문 (PK가 ticker, year, quarter이므로 중복 시 업데이트)
        sql = """
        INSERT INTO RND_TB (ticker, year, quarter, rnd_expense)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            rnd_expense = VALUES(rnd_expense);
        """
        
        # 튜플 리스트로 변환
        data_to_insert = [tuple(row) for row in df_to_db.values]
        
        # 일괄 적재
        cur.executemany(sql, data_to_insert)
        conn.commit()
        print(f"✅ R&D 데이터 {len(df_to_db)}건 적재 완료 (RND_TB)")

    except pymysql.err.IntegrityError as e:
        # FK 제약 조건 위반 시 (KOSPI200_STOCKS_TB에 없는 티커일 때) 발생
        print(f"❌ 외래 키 제약 조건 위반: {e}")
        print("💡 KOSPI200_STOCKS_TB에 해당 티커가 먼저 등록되어 있는지 확인하세요.")
    except Exception as e:
        print(f"❌ 기타 오류 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    load_rnd_to_db()