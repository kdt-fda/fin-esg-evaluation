from __future__ import annotations

import os
import json
import pymysql
import concurrent.futures
from dotenv import load_dotenv

from interpreter.llm_payload_builder import load_latest_short_result_from_db, load_latest_long_result_from_db
from interpreter.llm_generator import generate_combined_interpretation

load_dotenv()

def _connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4"
    )

def get_target_date_and_tickers():
    """가장 최근 단기 예측 날짜에 예측이 존재하고, LLM 해석 결과가 없는 모든 티커를 로드"""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(pred_date) FROM SHORT_PRED_TB")
            latest_date = cur.fetchone()[0]
            
            if not latest_date:
                return None, []

            sql = """
                SELECT p.ticker 
                FROM SHORT_PRED_TB p
                LEFT JOIN SHORT_LLM_TB l 
                    ON p.ticker = l.ticker AND p.pred_date = l.pred_date
                WHERE p.pred_date = %s AND l.ticker IS NULL
            """
            cur.execute(sql, (latest_date,))
            tickers = [row[0] for row in cur.fetchall()]
            
            return latest_date, tickers
    finally:
        conn.close()

def process_and_save_ticker(ticker: str, target_date):
    """단일 종목 해석 생성 및 DB 선택적 적재"""
    try:
        has_short = True
        has_long = True

        # 단기 데이터 로드 (없는 경우 빈 값 처리)
        try:
            short_res = load_latest_short_result_from_db(ticker)
        except ValueError:
            has_short = False
            short_res = {"stock_name": "", "ticker": ticker, "prediction": [], "shap_feature": [], "shap_value": []}

        # 장기 데이터 로드 (없는 경우 빈 값 처리)
        try:
            long_res = load_latest_long_result_from_db(ticker)
        except ValueError:
            has_long = False
            long_res = {"stock_name": short_res.get("stock_name", ""), "ticker": ticker, "score": None, "shap_feature": [], "shap_value": []}

        if not has_short and not has_long:
            return False, ticker, "단기/장기 예측 데이터가 모두 없습니다."
        
        # 종목명 추출
        stock_name = short_res.get("stock_name") or long_res.get("stock_name")

        # LLM 해석 생성
        interpretation = generate_combined_interpretation(short_result=short_res, long_result=long_res)

        # 데이터 선택적 DB 적재 (빈 값의 경우 적재 X)
        conn = _connect()
        try:
            with conn.cursor() as cur:
                short_term_data = interpretation.get("short_term")
                long_term_data = interpretation.get("long_term")

                if has_short and short_term_data:
                    short_json = json.dumps(short_term_data, ensure_ascii=False)
                    sql_short = """
                        INSERT INTO SHORT_LLM_TB (pred_date, ticker, interpretation)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE interpretation=VALUES(interpretation)
                    """
                    cur.execute(sql_short, (target_date, ticker, short_json))

                if has_long and long_term_data:
                    long_json = json.dumps(long_term_data, ensure_ascii=False)
                    sql_long = """
                        INSERT INTO LONG_LLM_TB (pred_date, ticker, interpretation)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE interpretation=VALUES(interpretation)
                    """
                    cur.execute(sql_long, (target_date, ticker, long_json))
            conn.commit()
        finally:
            conn.close()

        # 상태값 반환
        status_msg = "단기/장기 완료" if has_short and has_long else "단기만 완료" if has_short else "장기만 완료"
        return True, ticker, stock_name, status_msg

    except Exception as e:
        return False, ticker, str(e)

def run_llm_pipeline():
    """멀티스레딩으로 KOSPI 200 전체 종목 배치 처리"""
    target_date, tickers = get_target_date_and_tickers()

    if not target_date or not tickers:
        print("처리할 새로운 예측 데이터가 없습니다.")
        return

    print(f"🚀 예측 완료 종목 총 {len(tickers)}개 해석 시작 (기준일: {target_date})")
    
    success_count = 0
    fail_count = 0
    max_workers = 5
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_and_save_ticker, ticker, target_date): ticker for ticker in tickers}
        
        for future in concurrent.futures.as_completed(futures):
            success, ticker, stock_name, msg = future.result()
            if success:
                success_count += 1
                print(f"  ✅ [{success_count}/{len(tickers)}] {stock_name}({ticker}) ({msg})")
            else:
                fail_count += 1
                print(f"  ❌ [실패] {ticker}: {msg}")

    print(f"✅ LLM 해석 결과 업데이트 완료 (성공: {success_count}, 실패: {fail_count})")

if __name__ == "__main__":
    run_llm_pipeline()