import logging
import sys
import os
from datetime import datetime

# 프로젝트 루트 경로 추가 (모듈 참조용)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 각 스텝별 파이프라인 임포트
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
        # 결과값을 변수에 저장
        status = run_step1_pipeline()

        # 결과가 False(휴장일)이라면 함수 종료
        if status is False:
            logging.info("📅 휴장일로 인해 전체 프로세스를 종료합니다.")
            logging.info("="*50)
            return
        
        # 결과가 True(거래일)이라면 아래 단계 실행
        # [Step 2] 주가/거시경제/재무/뉴스 원천 데이터 수집
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
        # 여기에 텔레그램이나 이메일 알림 로직을 추가하면 완벽합니다.
        sys.exit(1)

if __name__ == "__main__":
    run_total_update_process()