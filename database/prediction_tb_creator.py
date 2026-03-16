import os
import pymysql
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

def create_prediction_tables():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 1. 단기 예측 테이블
            sql_short = """
                CREATE TABLE IF NOT EXISTS SHORT_PRED_TB (
                    pred_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    prediction JSON,
                    shap_feature JSON,
                    shap_value JSON,
                    dir_acc DECIMAL(10, 4),
                    mape DECIMAL(10, 4),
                    conf_score DECIMAL(10, 4),
                    PRIMARY KEY (pred_date, ticker),
                    FOREIGN KEY (ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                    ON DELETE CASCADE
                );
            """
            cur.execute(sql_short)
            print("✅ SHORT_PRED_TB 생성 완료 (DECIMAL 적용)")

            # 2. 중장기 예측 테이블
            sql_long = """
                CREATE TABLE IF NOT EXISTS LONG_PRED_TB (
                    pred_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    expected_ret DECIMAL(10, 4),
                    score DECIMAL(10, 4),
                    shap_feature JSON,
                    shap_value JSON,
                    dir_acc DECIMAL(10, 4),
                    hit_rate DECIMAL(10, 4),
                    rank_ic DECIMAL(10, 4),
                    ls_spread DECIMAL(10, 4),
                    conf_score DECIMAL(10, 4),
                    PRIMARY KEY (pred_date, ticker),
                    FOREIGN KEY (ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                    ON DELETE CASCADE
                );
            """
            cur.execute(sql_long)
            print("✅ LONG_PRED_TB 생성 완료 (DECIMAL 적용)")

            # 3. 단기 LLM 해석 테이블
            sql_short_llm = """
                CREATE TABLE IF NOT EXISTS SHORT_LLM_TB (
                    pred_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    interpretation TEXT,
                    PRIMARY KEY (pred_date, ticker),
                    FOREIGN KEY (ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                    ON DELETE CASCADE
                );
            """
            cur.execute(sql_short_llm)
            print("✅ SHORT_LLM_TB 생성 완료")

            # 4. 중장기 LLM 해석 테이블
            sql_long_llm = """
                CREATE TABLE IF NOT EXISTS LONG_LLM_TB (
                    pred_date DATE NOT NULL,
                    ticker VARCHAR(10) NOT NULL,
                    interpretation TEXT,
                    PRIMARY KEY (pred_date, ticker),
                    FOREIGN KEY (ticker) REFERENCES KOSPI200_STOCKS_TB(ticker)
                    ON DELETE CASCADE
                );
            """
            cur.execute(sql_long_llm)
            print("✅ LONG_LLM_TB 생성 완료")
            
        conn.commit()
        
    except Exception as e:
        print(f"❌ 테이블 생성 중 오류 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    create_prediction_tables()