import datetime
import logging
from scripts.stock_crawler import run_stock_crawler
from scripts.macro_collector import run_macro_collector
from scripts.fundamental_crawler import run_fundamental_crawler
from scripts.news_processor import run_news_processor

def is_quarterly_update_time():
    """
    재무제표 공시 시즌(3, 5, 8, 11월)인지 체크
    실적 공시가 보통 나오는 달의 15일 이후부터 말일까지 업데이트 수행
    """
    today = datetime.date.today()
    return today.month in [3, 5, 8, 11] and today.day >= 15

def run_step2_pipeline():
    """
    main_updater.py에서 호출할 메인 함수
    """
    logging.info("--- Step 2: 시장 데이터(주가/거시/재무) 수집 시작 ---")
    
    try:
        # 1. 주가 데이터 (매일 업데이트)
        logging.info("1. 주가 데이터 수집 중...")
        print("1. 주가 데이터 업데이트 중...")
        run_stock_crawler()
        
        # 2. 거시경제 데이터 (발표 시간에 따라 에러 발생 잦으므로 try-except)
        try:
            logging.info("2. 거시경제 지표 수집 중...")
            print("2. 거시경제 지표 업데이트 중...")
            run_macro_collector(is_initial=False)
        except Exception as macro_e:
            logging.warning(f"⚠️ 거시경제 데이터 수집 중 일부 실패 (진행 가능): {macro_e}")
            print(f"⚠️ 거시경제 지표 일부 수집 실패. 다음 단계로 진행합니다.")
        
        # 3. 펀더멘털 데이터 (분기별 체크)
        if is_quarterly_update_time():
            logging.info("3. 공시 시즌 - 펀더멘털 데이터 업데이트 중...")
            print("3. 실적 공시 시즌입니다. 펀더멘털 데이터 업데이트 중...")
            run_fundamental_crawler()
        else:
            logging.info("3. 펀더멘털: 공시 시즌이 아니므로 건너뜁니다.")
            print("3. 펀더멘털: 현재 공시 시즌이 아니므로 건너뜁니다.")
        
        # 4. 뉴스 데이터 (매일 업데이트)
        logging.info("4. 뉴스 데이터 프로세싱 대기 중...")
        print("4. 뉴스 감성 분석 데이터 업데이트 중...")
        run_news_processor()

        logging.info("Step 2 모든 수집 및 적재 완료.")
        print("\n✅ Step 2 성공적으로 완료되었습니다.")

    except Exception as e:
        logging.error(f"Step 2 수행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        print(f"❌ Step 2 실패: {e}")
        raise e  # main_updater에서 실패를 감지할 수 있도록 에러를 던짐