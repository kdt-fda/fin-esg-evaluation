import pymysql
import os
import requests
import pandas as pd
import random
from pykrx import stock
from pykrx.website.comm import webio
from datetime import datetime
import time
from dotenv import load_dotenv
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

load_dotenv()

# ==========================================
# 세션 패치 및 방화벽 우회 패치
# ==========================================
_session = requests.Session()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def _get_fake_ip():
    return f"211.{random.randint(100, 250)}.{random.randint(1, 250)}.{random.randint(1, 250)}"

_session.headers.update({
    "User-Agent": _UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "http://data.krx.co.kr/"
})

retry_strategy = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[403, 429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
_session.mount('http://', adapter)
_session.mount('https://', adapter)

def _safe_post(self, **params):
    headers = getattr(self, 'headers', {}).copy() if getattr(self, 'headers', None) else {}
    headers['User-Agent'] = _UA
    headers['Referer'] = "http://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd" 
    headers['Origin'] = "http://data.krx.co.kr" 
    headers['X-Requested-With'] = "XMLHttpRequest" 
    fake_ip = _get_fake_ip()
    headers['X-Forwarded-For'] = fake_ip
    headers['X-Real-IP'] = fake_ip
    return _session.post(self.url, headers=headers, data=params, timeout=30)

def _safe_get(self, **params):
    headers = getattr(self, 'headers', {}).copy() if getattr(self, 'headers', None) else {}
    headers['User-Agent'] = _UA
    headers['Referer'] = "http://data.krx.co.kr/"
    fake_ip = _get_fake_ip()
    headers['X-Forwarded-For'] = fake_ip
    headers['X-Real-IP'] = fake_ip
    return _session.get(self.url, headers=headers, params=params, timeout=30)

webio.Post.read = _safe_post
webio.Get.read = _safe_get

def _connect():
    host = os.environ.get('DB_HOST')
    port = int(os.environ.get('DB_PORT'))
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=db_name, connect_timeout=10
    )
    return conn

def login_to_krx():
    KRX_ID = os.getenv("KRX_ID")
    KRX_PW = os.getenv("KRX_PW")
    
    if not KRX_ID or not KRX_PW:
        print("⚠️ KRX 계정 정보가 없습니다. 익명 세션으로 진행합니다.")
        return False

    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

    try:
        fake_ip = _get_fake_ip()
        login_headers = {"X-Forwarded-For": fake_ip, "X-Real-IP": fake_ip}

        _session.get(_LOGIN_PAGE, headers=login_headers)
        _session.get(_LOGIN_JSP, headers=login_headers)
        payload = {"mbrId": KRX_ID, "pw": KRX_PW}
        resp = _session.post(_LOGIN_URL, data=payload, headers=login_headers)
        
        if resp.json().get("_error_code") in ["CD001", "CD011"]:
            print("✅ KRX 로그인 성공")
            return True
        return False
    except:
        return False

def update_kospi200_stocks_table():
    login_to_krx()
    
    today = datetime.now().strftime("%Y%m%d")
    print(f"📋 [{today}] 코스피 종목 마스터 정보 로딩 중...")
    
    try:
        all_tickers = stock.get_market_ticker_list(today, market="KOSPI")
        ticker_name_map = {t: stock.get_market_ticker_name(t) for t in all_tickers}
    except Exception as e:
        print(f'마스터 정보 로딩 실패: {e}')
        return

    sector_map = {
        'COMM': '1150', 'CONS': '1151', 'HI': '1152', 'MAT': '1153',
        'ENG': '1154', 'IT': '1155', 'FIN': '1156', 'CS': '1157',
        'CD': '1158', 'IND': '1159', 'HC': '1160'
    }

    data = []
    try:
        for eng_code, krx_code in sector_map.items():
            tickers = []

            for attempt in range(3):
                try:
                    tickers_raw = stock.get_index_portfolio_deposit_file(krx_code, today)
                    
                    if isinstance(tickers_raw, pd.DataFrame):
                        if not tickers_raw.empty:
                            tickers = tickers_raw.index.tolist()
                    elif isinstance(tickers_raw, list):
                        tickers = tickers_raw

                    if len(tickers) > 0:
                        break
                    else:
                        print(f"⚠️ {eng_code} 섹터 0건 수집. 재시도... ({attempt+1}/3)")
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"❌ {eng_code} 파이썬 에러 발생: {e}")
                    time.sleep(0.5)

            if not tickers:
                continue

            for ticker in tickers:
                stock_name = ticker_name_map.get(ticker, "Unknown")
                data.append((ticker, stock_name, eng_code, True))

            print(f"✅ {eng_code} 섹터 수집 완료 ({len(tickers)} 종목)")
            time.sleep(0.5)

        if data:
            conn = _connect()
            try:
                cur = conn.cursor(pymysql.cursors.DictCursor)
                cur.execute('UPDATE KOSPI200_STOCKS_TB SET is_active = FALSE;')

                sql = """
                    INSERT INTO KOSPI200_STOCKS_TB (ticker, stock_name, sector_code, is_active)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    stock_name = VALUES(stock_name),
                    sector_code = VALUES(sector_code),
                    is_active = VALUES(is_active);
                    """
                cur.executemany(sql, data)
                conn.commit()
                print(f'[{datetime.now()}] KOSPI200 {len(data)}개 종목 업데이트 완료')
            except Exception as e:
                print(f"DB 적재 오류: {e}")
                conn.rollback()
            finally:
                conn.close()
        else:
            print("⚠️ 수집된 종목 데이터가 없습니다.")
    except Exception as e:
        print(f'❌ 수집 과정 오류: {e}')

if __name__ == '__main__':
    update_kospi200_stocks_table()