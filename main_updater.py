import sys

try:
    import pkg_resources
except ImportError:
    try:
        from pip._vendor import pkg_resources
    except ImportError:
        import setuptools.pkg_resources as pkg_resources
    sys.modules["pkg_resources"] = pkg_resources

import logging
import os
import time
import schedule
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.step1_base_updater import run_step1_pipeline
from scripts.step2_market_data_updater import run_step2_pipeline
from scripts.step3_indicator_calculator import run_step3_pipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("update_log.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger("pykrx").setLevel(logging.CRITICAL)
logging.getLogger("huggingface_hub").setLevel(logging.CRITICAL)
logging.getLogger("transformers").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("filelock").setLevel(logging.CRITICAL)
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'

def run_total_update_process():
    """전체 데이터 갱신 프로세스 통합 컨트롤러"""
    total_start_time = datetime.now()
    durations = {}

    logging.info("="*50)
    logging.info("🚀 데이터 업데이트 시스템 가동 시작")
    logging.info("="*50)

    try:
        step1_start = datetime.now()
        logging.info("Step 1. 종목/섹터 마스터 데이터 업데이트 중...")
        is_bday = run_step1_pipeline()
        durations['Step 1'] = datetime.now() - step1_start

        if not is_bday:
            logging.info("오늘은 휴장일입니다.")

        logging.info("⏳ Step 1 완료. 서버 부하 방지를 위해 5초간 대기합니다...")
        time.sleep(5)
        
        step2_start = datetime.now()
        logging.info("Step 2. 원천 데이터(주가/거시경제/재무/뉴스) 수집 및 적재 중...")
        run_step2_pipeline(is_bday=is_bday)
        durations['Step 2'] = datetime.now() - step2_start

        logging.info("⏳ Step 2 완료. 서버 부하 방지를 위해 5초간 대기합니다...")
        time.sleep(5)

        step3_start = datetime.now()
        logging.info("Step 3. 파생 지표 계산 및 퀀트 DB 최종 적재 중...")
        run_step3_pipeline(is_bday=is_bday)
        durations['Step 3'] = datetime.now() - step3_start

        total_duration = datetime.now() - total_start_time
        logging.info("="*50)
        logging.info("📊 업데이트 완료 리포트")
        for step, duration in durations.items():
            logging.info(f" - {step}: {duration}")
        logging.info(f"✨ 전체 총 소요시간: {total_duration}")
        logging.info("="*50)

    except Exception as e:
        logging.critical(f"🚨 시스템 중단 발생: {str(e)}", exc_info=True)

if __name__ == "__main__":
    schedule.every().day.at("23:30").do(run_total_update_process)
    logging.info("⏰ 스케줄러 활성화: 매일 23:30에 업데이트를 시작합니다.")

    while True:
        schedule.run_pending()
        time.sleep(60)