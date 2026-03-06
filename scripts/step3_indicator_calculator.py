import logging
from datetime import datetime
from scripts.common_calculator import run_common_indicator_calculator
from scripts.sector_calculator import run_sector_indicator_calculator

def run_step3_pipeline():
    """
    Step 3: 파생 지표(시장/섹터) 계산 및 적재
    """
    logging.info("--- Step 3: 파생 지표 및 퀀트 데이터 업데이트 시작 ---")
    
    try:
        logging.info("1. 공통 파생 지표 업데이트 중...")
        run_common_indicator_calculator()
        
        logging.info("2. 섹터별 파생 지표 업데이트 중...")
        run_sector_indicator_calculator()

        logging.info("Step 3 파생 지표 계산 및 적재 완료")

    except Exception as e:
        logging.error(f"Step 3 수행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        print(f"❌ Step 3 실패: {e}")
        raise e