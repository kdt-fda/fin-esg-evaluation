import logging
from datetime import datetime
from crawler.common_calculator import run_common_indicator_calculator
from crawler.sector_calculator import run_sector_indicator_calculator

def run_step3_pipeline(is_bday=True):
    """main_updater.py에서 호출할 Step 3 함수 (공통/섹터별 파생 지표)"""
    logging.info("--- Step 3: 파생 지표 및 퀀트 데이터 업데이트 시작 ---")

    try:
        if is_bday:
            logging.info("1. 공통 파생 지표 업데이트 중...")
            run_common_indicator_calculator()
        
            logging.info("2. 섹터별 파생 지표 업데이트 중...")
            run_sector_indicator_calculator()

            logging.info("Step 3 파생 지표 계산 및 적재 완료")
        
        else:
            logging.info("💤 오늘은 휴장일입니다. 파생 지표 업데이트를 생략합니다.")

    except Exception as e:
        logging.error(f"Step 3 수행 중 오류 발생: {str(e)}", exc_info=True)
        print(f"❌ Step 3 실패: {e}")
        raise e