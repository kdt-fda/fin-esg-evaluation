import time
import schedule
import logging
import os
from datetime import datetime
from pykrx import stock

# 기존 업데이트 함수들 임포트
from database.sector_tb_updater import update_sector_table
from database.kospi200_stocks_tb_updater import update_kospi200_stocks_table

# 로그 설정: 'automation.log' 파일에 시간과 함께 기록 저장
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    filename=os.path.join(log_dir, f'automation_{datetime.now().strftime("%Y%m")}.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

def is_business_day():
    today = datetime.now().strftime("%Y%m%d")
    df = stock.get_market_ohlcv(today, today, "005930")
    return not df.empty

def daily_update():
    logging.info("기본 데이터 업데이트 작업을 시작합니다.")
    
    if not is_business_day():
        logging.info("오늘은 휴장일(또는 데이터 미생성일)이므로 작업을 건너뜁니다.")
        return

    try:
        logging.info("1. 섹터 정보 업데이트 중...")
        update_sector_table()
        
        logging.info("2. 코스피 200 종목 및 섹터 매핑 업데이트 중...")
        update_kospi200_stocks_table()
        
        logging.info("모든 업데이트 작업이 성공적으로 완료되었습니다.")
        print(f"[{datetime.now()}] 업데이트 완료 (로그 확인 요망)")
    except Exception as e:
        logging.error(f"작업 수행 중 오류 발생: {str(e)}", exc_info=True)

def run_scheduler():
    # 매일 오후 4시에 실행
    schedule.every().day.at("16:00").do(daily_update)
    
    logging.info("스케줄러가 시작되었습니다. 매일 오후 4시에 실행됩니다.")
    print("스케줄러 가동 중... 로그는 logs/ 폴더에서 확인하세요.")

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logging.critical(f"스케줄러 루프 중 치명적 오류 발생: {e}")
            time.sleep(60) # 오류 발생 시 잠시 대기 후 재시도

if __name__ == '__main__':
    # 최초 실행 시 업데이트를 한번 확인하고 싶다면 아래 주석 해제
    # daily_update()
    
    run_scheduler()