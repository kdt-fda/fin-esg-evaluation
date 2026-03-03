import requests
import os
from pykrx import stock
from pykrx.website.comm import webio
from dotenv import load_dotenv

# 1. 환경 변수 로드 (.env 파일에 KRX_ID, KRX_PW가 있어야 함)
load_dotenv()

# 2. 세션 패치 (pykrx 통신망 교체)
_session = requests.Session()
webio.Post.read = lambda self, **params: _session.post(self.url, headers=self.headers, data=params)
webio.Get.read = lambda self, **params: _session.get(self.url, headers=self.headers, params=params)

def test_login_and_fetch():
    # 3. 로그인 시도
    KRX_ID = os.getenv("KRX_ID")
    KRX_PW = os.getenv("KRX_PW")
    
    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    print("🔑 KRX 로그인 시도 중...")
    _session.get(_LOGIN_PAGE, headers={"User-Agent": _UA}, timeout=15)
    _session.get(_LOGIN_JSP, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE}, timeout=15)
    
    payload = {"mbrId": KRX_ID, "pw": KRX_PW}
    resp = _session.post(_LOGIN_URL, data=payload, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
    
    result = resp.json()
    if result.get("_error_code") == "CD001" or result.get("_error_code") == "CD011":
        print("✅ 로그인 성공 (또는 중복 로그인 허용)")
        
        # 4. 수급 데이터 수집 테스트 (삼성전자, 최근 3일)
        print("\n📊 삼성전자(005930) 수급 데이터 호출 테스트...")
        df = stock.get_market_trading_value_by_date("20260225", "20260302", "005930")
        
        if df.empty:
            print("❌ 실패: 데이터프레임이 비어 있습니다. (로그인은 됐으나 구조가 여전히 다름)")
        else:
            print("✅ 성공: 데이터를 정상적으로 가져왔습니다!")
            print(df.head())
    else:
        print(f"❌ 로그인 실패: {result.get('_error_msg', '알 수 없는 오류')}")

if __name__ == "__main__":
    test_login_and_fetch()