import logging
import sys
import os
import time
import schedule
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.step1_base_updater import run_step1_pipeline
from scripts.step2_market_data_updater import run_step2_pipeline
from scripts.step3_indicator_calculator import run_step3_pipeline

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("update_log.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def run_total_update_process():
    """전체 데이터 갱신 프로세스 통합 컨트롤러"""
    start_time = datetime.now()
    logging.info("="*50)
    logging.info("🚀 데이터 업데이트 시스템 가동 시작")
    logging.info("="*50)

    try:
        # [Step 1] 종목 및 섹터 기본 정보 갱신
        logging.info("Step 1. 종목/섹터 마스터 데이터 업데이트 중...")
        status = run_step1_pipeline()

        if status is False:
            logging.info("📅 휴장일로 인해 전체 프로세스를 종료합니다.")
            logging.info("="*50)
            return
        
        # [Step 2] 원천 데이터 수집
        logging.info("Step 2. 원천 데이터(주가/거시경제/재무/뉴스) 수집 및 적재 중...")
        run_step2_pipeline()
        
        # [Step 3] 파생 지표 계산 및 퀀트 DB 적재
        logging.info("Step 3. 파생 지표 계산 및 퀀트 DB 최종 적재 중...")
        run_step3_pipeline()

        duration = datetime.now() - start_time
        logging.info("="*50)
        logging.info(f"✨ 전체 프로세스 성공적 완료! (총 소요시간: {duration})")
        logging.info("="*50)

    except Exception as e:
        logging.critical(f"🚨 시스템 중단 발생: {str(e)}", exc_info=True)
        # 여기에 이메일 알림 함수를 호출하면 좋습니다.

if __name__ == "__main__":
    # 매일 22:00분에 실행되도록 예약
    schedule.every().day.at("22:00").do(run_total_update_process)
    
    logging.info("⏰ 스케줄러 활성화: 매일 22:00에 업데이트를 시작합니다.")

    # 무한 루프를 돌며 정해진 시간이 되었는지 체크
    while True:
        schedule.run_pending()
        time.sleep(60)  # 1분마다 체크하여 리소스 낭비 방지