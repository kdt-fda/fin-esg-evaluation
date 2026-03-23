import sys
import os
import time
import schedule
import logging
from datetime import datetime
from pykrx import stock

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from analyzer.short_analyzer import run_short_term_pipeline
from analyzer.long_analyzer import run_long_term_pipeline

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class OnlyMyCodeFilter(logging.Filter):
    def filter(self, record):
        if record.pathname.startswith(PROJECT_ROOT):
            if "site-packages" not in record.pathname:
                return True
        return False

os.makedirs("logs", exist_ok=True)
    
file_handler = logging.FileHandler("logs/analyze_log.log", encoding='utf-8')
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

def is_business_day():
    """오늘이 개장일인지 확인"""
    try:
        today_str = datetime.now().strftime("%Y%m%d")
        
        df = stock.get_market_ohlcv(today_str, today_str, "005930")
        if df is None or df.empty:
            return False
        return True
        
    except Exception as e:
        logging.warning(f'개장일 확인 중 에러 발생 (서버 응답 불안정): {e}')
        logging.info("영업일로 간주하고 계속 진행")
        return True

def run_total_analysis_process():
    """전체 AI 예측/분석 프로세스 통합 컨트롤러"""

    if not is_business_day():
        logging.info("💤 오늘은 휴장일입니다. 모델 예측을 건너뜁니다.")
        return
    
    total_start_time = datetime.now()
    durations = {}

    logging.info("="*50)
    logging.info("🌟 예측 모델 파이프라인 가동 시작")
    logging.info("="*50)

    try:
        step1_start = datetime.now()
        logging.info("Step 1. 단기 예측 모델 가동...")
        
        run_short_term_pipeline(win=10, horizon=20)
        
        durations['단기 예측 모델'] = datetime.now() - step1_start
        logging.info("⏳ 단기 예측 완료. 서버 부하 방지를 위해 5초간 대기합니다...")
        time.sleep(5)

        step2_start = datetime.now()
        logging.info("Step 2. 중장기 예측 모델 가동...")
        
        run_long_term_pipeline()
        
        durations['중장기 예측 모델'] = datetime.now() - step2_start
        logging.info("⏳ 중장기 예측 완료.")

        total_duration = datetime.now() - total_start_time
        logging.info("="*50)
        logging.info("🎉 예측 및 분석 완료 리포트")
        for step, duration in durations.items():
            logging.info(f" - {step}: {duration}")
        logging.info(f"✨ 전체 총 소요시간: {total_duration}")
        logging.info("="*50)

    except Exception as e:
        logging.critical(f"🚨 시스템 중단 발생: {str(e)}", exc_info=True)

if __name__ == "__main__":
    schedule.every().day.at("22:30").do(run_total_analysis_process)
    logging.info("⏰ 분석기 스케줄러: 매일 22:30에 업데이트를 시작합니다.")

    while True:
        schedule.run_pending()
        time.sleep(60)