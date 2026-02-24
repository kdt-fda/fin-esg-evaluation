import os
import sys
import logging
from datetime import datetime

# 모듈 참조를 위한 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 각각의 모듈에서 실행 함수를 불러옵니다.
try:
    from scripts.common_calculator import run_common_indicator_calculator
    from scripts.sector_calculator import run_sector_indicator_calculator
except ImportError:
    # 스크립트 직접 실행 시를 위한 상대 경로 처리
    from common_calculator import run_common_indicator_calculator
    from sector_calculator import run_sector_indicator_calculator

def run_step3_pipeline():
    """
    Step 3: 파생 지표(시장/섹터) 계산 및 적재
    """
    logging.info("--- Step 3: 파생 지표 및 퀀트 데이터 업데이트 시작 ---")
    start_time = datetime.now()
    
    try:
        # 1. 공통 시장 지표 (KOSPI200 MA, Regime, CLI 등)
        logging.info("1. 공통 시장 지표(COMMON_TB) 업데이트 중...")
        print("1. 공통 시장 지표 업데이트 중...")
        run_common_indicator_calculator()
        
        # 2. 11개 섹터별 특화 지표 (IT_TB, FIN_TB 등)
        logging.info("2. 11개 섹터별 특화 파생 지표 업데이트 중...")
        print("2. 섹터별 파생 지표(11개 섹터) 업데이트 중...")
        run_sector_indicator_calculator()

        duration = datetime.now() - start_time
        logging.info(f"Step 3 모든 지표 계산 및 적재 완료. (소요시간: {duration})")
        print(f"\n✅ Step 3 성공적으로 완료되었습니다. (소요시간: {duration})")

    except Exception as e:
        logging.error(f"Step 3 수행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        print(f"❌ Step 3 실패: {e}")
        raise e  # main_updater에서 실패를 감지할 수 있도록 에러를 던짐

if __name__ == "__main__":
    # 개별 테스트용 로깅 설정
    logging.basicConfig(level=logging.INFO)
    run_step3_pipeline()