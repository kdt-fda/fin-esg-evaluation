import time
import schedule
from datetime import datetime
from pykrx import stock

from sector_tb_updater import update_sector_table
from kospi200_stocks_tb_updater import update_kospi200_stocks_table

def is_business_day():
    today = datetime.now().strftime("%Y%m%d")
    # 오늘 날짜의 개장 여부를 확인
    # pykrx의 get_market_ohlcv는 휴장일일 경우 빈 데이터프레임을 반환합니다.
    df = stock.get_market_ohlcv(today, today, "005930") # 삼성전자 기준 확인
    return not df.empty

def daily_update():
    # 매일 수행할 작업
    print(f"[{datetime.now()}] 기본 데이터 업데이트 작업을 시작합니다.")
    
    if not is_business_day():
        print(f"[{datetime.now()}] 오늘은 휴장일(또는 데이터 미생성일)이므로 작업을 건너뜁니다.")
        return

    try:
        print("1. 섹터 정보 업데이트 중...")
        update_sector_table()
        
        print("2. 코스피 200 종목 및 섹터 매핑 업데이트 중...")
        update_kospi200_stocks_table()
        
        print(f"[{datetime.now()}] 모든 업데이트 작업이 성공적으로 완료되었습니다.")
    except Exception as e:
        print(f"[{datetime.now()}] 작업 수행 중 오류 발생: {e}")

def run_scheduler():
    # 스케줄러 설정: 매일 16:00에 실행
    schedule.every().day.at("16:00").do(daily_update)
    
    print("==========================================")
    print("스케줄러가 시작되었습니다.")
    print("매일 오후 4시에 데이터를 수집합니다.")
    print("==========================================")

    while True:
        schedule.run_pending()
        time.sleep(60) # 1분마다 체크

if __name__ == '__main__':
    daily_update() 
    
    run_scheduler()