import logging
from datetime import datetime
from pykrx import stock
from database.sector_tb_updater import update_sector_table
from database.kospi200_stocks_tb_updater import update_kospi200_stocks_table

def is_business_day():
    """오늘이 개장일인지 확인"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        df = stock.get_market_ohlcv(today, today, "005930", timeout=10)
        if df.empty:
            return False
        return True
    except Exception as e:
        logging.warning(f'개장일 확인 중 에러 발생 (서버 응답 불안정): {e}')
        logging.info("영업일로 간주하고 계속 진행")
        return True

def run_step1_pipeline():
    """main_updater.py에서 호출할 메인 함수"""
    logging.info("--- Step 1: 기본 데이터 업데이트 시작 ---")
    
    if not is_business_day():
        logging.info("오늘은 휴장일이므로 Step 1 작업을 건너뜁니다.")
        return False

    try:
        logging.info("1. 섹터 정보 업데이트 중...")
        update_sector_table()
        
        logging.info("2. 코스피 200 종목 및 섹터 매핑 업데이트 중...")
        update_kospi200_stocks_table()
        
        logging.info("Step 1 기준 데이터 업데이트 완료")
        return True
    except Exception as e:
        logging.error(f"Step 1 수행 중 오류 발생: {str(e)}", exc_info=True)
        raise e