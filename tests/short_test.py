import requests
import pandas as pd
from pykrx import stock
from pykrx.website.comm import webio
from datetime import datetime
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ==========================================
# 0. 세션 위장 (방화벽 우회)
# ==========================================
_session = requests.Session()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

_session.headers.update({
    "User-Agent": _UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "http://data.krx.co.kr/"
})

retry_strategy = Retry(total=5, backoff_factor=1, status_forcelist=[403, 429, 500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
_session.mount('http://', adapter)
_session.mount('https://', adapter)

def _safe_post(self, **params):
    headers = getattr(self, 'headers', {}).copy() if getattr(self, 'headers', None) else {}
    headers['User-Agent'] = _UA
    headers['Referer'] = "http://data.krx.co.kr/"
    return _session.post(self.url, headers=headers, data=params, timeout=15)

def _safe_get(self, **params):
    headers = getattr(self, 'headers', {}).copy() if getattr(self, 'headers', None) else {}
    headers['User-Agent'] = _UA
    headers['Referer'] = "http://data.krx.co.kr/"
    return _session.get(self.url, headers=headers, params=params, timeout=15)

webio.Post.read = _safe_post
webio.Get.read = _safe_get

today = datetime.now().strftime("%Y%m%d")

print("="*50)
print(f"🚀 KRX 트러블슈팅 테스트 시작 (기준일: {today})")
print("="*50)

# ==========================================
# 🧪 테스트 1: KOSPI 200 섹터 종목 수집 테스트 (함수 변경완료!)
# ==========================================
print("\n[테스트 1] KOSPI 200 섹터(IT: 1155) 구성종목 수집")
try:
    krx_code_it = "1155" # KOSPI 200 정보통신
    
    # 🚨 ETF 함수가 아닌 지수 구성종목 전용 함수 사용
    print(f"👉 시도: stock.get_index_ticker_list('{today}', '{krx_code_it}')")
    tickers = stock.get_index_ticker_list(today, krx_code_it)
    
    if tickers and len(tickers) > 0:
        print(f"✅ 성공! 총 {len(tickers)}개 종목 수집됨.")
        print(f"📌 샘플(앞 5개): {tickers[:5]}")
    else:
        print("❌ 실패: 여전히 0건이 수집됩니다.")
except Exception as e:
    print(f"❌ 에러 발생: {e}")

# ==========================================
# 🧪 테스트 2: 개장일(영업일) 판별 로직 테스트
# ==========================================
print("\n[테스트 2] 개장일(영업일) 판별 로직")
try:
    # pykrx를 이용한 가장 안전한 영업일 판별법
    year = today[:4]
    month = today[4:6]
    
    # 해당 월의 영업일 리스트(DatetimeIndex)를 가져옴
    b_days = stock.get_business_days(year, month)
    
    # 오늘 날짜가 영업일 리스트에 포함되어 있는지 확인
    today_dt = pd.to_datetime(today)
    is_bday = today_dt in b_days
    
    print("✅ 에러 없이 실행 성공!")
    print(f"📌 오늘({today_dt.date()})은 영업일입니까? -> {is_bday}")
    
except Exception as e:
    print(f"❌ 에러 발생: {e}")

print("\n" + "="*50)
print("🏁 테스트 종료")
print("="*50)