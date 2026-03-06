import logging
import datetime
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
        logging.info("1. 주가 데이터 수집 중...")
        run_stock_crawler()
        
        logging.info("2. 거시경제 지표 수집 중...")
        run_macro_collector(is_initial=False)
        
        if is_quarterly_update_time():
            logging.info("3. 공시 시즌 - 펀더멘털 데이터 업데이트 중...")
            run_fundamental_crawler()
        else:
            logging.info("3. 펀더멘털 지표 공시 시즌이 아닙니다.")
        
        logging.info("4. 뉴스 데이터 파이프라인 수행 중...")
        run_news_processor()

        logging.info("Step 2 각종 지표 수집 및 적재 완료")

    except Exception as e:
        logging.error(f"Step 2 수행 중 치명적 오류 발생: {str(e)}", exc_info=True)
        print(f"❌ Step 2 실패: {e}")
        raise e