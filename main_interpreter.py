import sys
import os
import time
import schedule
import logging
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from interpreter.llm_processor import run_llm_pipeline

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class OnlyMyCodeFilter(logging.Filter):
    def filter(self, record):
        if record.pathname.startswith(PROJECT_ROOT):
            if "site-packages" not in record.pathname:
                return True
        return False

os.makedirs("logs", exist_ok=True)

file_handler = logging.FileHandler("logs/interpret_log.log", encoding='utf-8')
stream_handler = logging.StreamHandler()

my_filter = OnlyMyCodeFilter()
file_handler.addFilter(my_filter)
stream_handler.addFilter(my_filter)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[file_handler, stream_handler],
    force=True
)

def run_total_interpretation_process():
    """전체 AI 해석(LLM) 프로세스 통합 컨트롤러"""

    logging.info("="*50)
    logging.info("🌟 AI 해석기 파이프라인 가동 시작")
    logging.info("="*50)

    try:
        start = datetime.now()
        logging.info("단기 / 중장기 LLM 해석 파이프라인 가동...")

        run_llm_pipeline()
        
        logging.info("⏳ LLM 리포트 생성 완료.")

        duration = datetime.now() - start
        logging.info("="*50)
        logging.info("🎉 해석 완료 리포트")
        logging.info(f"✨ 전체 총 소요시간: {duration}")
        logging.info("="*50)

    except Exception as e:
        logging.critical(f"🚨 시스템 중단 발생: {str(e)}", exc_info=True)

if __name__ == "__main__":
    schedule.every().day.at("23:00").do(run_total_interpretation_process)
    logging.info("⏰ 해석기 스케줄러: 매일 23:00에 업데이트를 시작합니다.")

    while True:
        schedule.run_pending()
        time.sleep(60)