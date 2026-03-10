import requests
import os
from pykrx import stock
from pykrx.website.comm import webio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# 1. 전역 세션 및 패치
_session = requests.Session()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# pykrx 내부 통신을 우리 세션으로 연결
webio.Post.read = lambda self, **params: _session.post(self.url, headers=self.headers, data=params, timeout=15)
webio.Get.read = lambda self, **params: _session.get(self.url, headers=self.headers, params=params, timeout=15)

def verify_and_fetch(ticker="000080"): # 삼성전자 기준
    KRX_ID = os.getenv("KRX_ID")
    KRX_PW = os.getenv("KRX_PW")
    
    print(f"--- [1] KRX 로그인 시도 ({KRX_ID}) ---")
    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

    try:
        # [Step 1] 메인 페이지 접속 (쿠키 획득)
        _session.get(_LOGIN_PAGE, headers={"User-Agent": _UA})
        # [Step 2] 로그인 폼 JSP 접근 (세션 유효성 확보)
        _session.get(_LOGIN_JSP, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
        
        # [Step 3] 실제 로그인 POST
        payload = {"mbrId": KRX_ID, "pw": KRX_PW}
        resp = _session.post(_LOGIN_URL, data=payload, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
        
        print(f"로그인 응답 코드: {resp.status_code}")
        print(f"로그인 결과: {resp.json().get('_error_code', 'Unknown')} (CD001이면 성공)")

        # 세션 쿠키 확인
        print(f"현재 획득한 쿠키 개수: {len(_session.cookies)}")

        # [Step 4] 공매도 데이터 수집 테스트
        print(f"\n--- [2] {ticker} 공매도 데이터 수집 테스트 ---")
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        
        df = stock.get_shorting_balance_by_date(start_date, end_date, ticker)
        
        if df.empty:
            print("❌ 결과: 데이터프레임이 비어있습니다. (세션 문제 혹은 데이터 미공시)")
        else:
            print(f"✅ 결과: {len(df)}행 데이터 수신 성공!")
            print(df.tail(5))
            
            # 컬럼명 확인
            print(f"사용 가능한 컬럼들: {df.columns.tolist()}")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    verify_and_fetch()