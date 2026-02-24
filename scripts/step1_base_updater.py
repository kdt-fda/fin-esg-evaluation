import logging
import os
from datetime import datetime
from pykrx import stock
from database.sector_tb_updater import update_sector_table
from database.kospi200_stocks_tb_updater import update_kospi200_stocks_table

def is_business_day():
    today = datetime.now().strftime("%Y%m%d")
    df = stock.get_market_ohlcv(today, today, "005930")
    return not df.empty

def run_step1_pipeline():
    """main_updater.py에서 호출할 메인 함수"""
    logging.info("--- Step 1: 기본 데이터 업데이트 시작 ---")
    
    if not is_business_day():
        logging.info("오늘은 휴장일이므로 Step 1 작업을 건너뜁니다.")
        return False # 휴장일임을 알림

    try:
        logging.info("\n1. 섹터 정보 업데이트 중...")
        update_sector_table()
        
        logging.info("\n2. 코스피 200 종목 및 섹터 매핑 업데이트 중...")
        update_kospi200_stocks_table()
        
        logging.info("\nStep 1 모든 업데이트 완료.")
        return True # 성공적으로 완료됨을 알림
    except Exception as e:
        logging.error(f"Step 1 수행 중 오류 발생: {str(e)}", exc_info=True)
        raise e  # 메인 스케줄러에서 에러를 인지할 수 있도록 전달