import os
import requests
import pandas as pd
from pykrx import stock
from pykrx.website.comm import webio
from dotenv import load_dotenv
from datetime import datetime

# 1. 환경 변수 로드
load_dotenv()

# 2. 세션 패치 (본 코드와 동일하게 설정)
_session = requests.Session()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
webio.Post.read = lambda self, **params: _session.post(self.url, headers=self.headers, data=params, timeout=15)
webio.Get.read = lambda self, **params: _session.get(self.url, headers=self.headers, params=params, timeout=15)

def debug_fetch():
    # 3. 로그인 시도 (테스트 성공 버전)
    KRX_ID = os.getenv("KRX_ID")
    KRX_PW = os.getenv("KRX_PW")
    
    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"

    print("Step 1: 🔑 KRX 로그인 시도...")
    _session.get(_LOGIN_PAGE, headers={"User-Agent": _UA})
    _session.get(_LOGIN_JSP, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
    resp = _session.post(_LOGIN_URL, data={"mbrId": KRX_ID, "pw": KRX_PW}, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE})
    
    if resp.json().get("_error_code") not in ["CD001", "CD011"]:
        print(f"❌ 로그인 실패: {resp.json().get('_error_msg')}")
        return

    print("✅ 로그인 성공!")

    # 4. 데이터 수집 단계별 추적
    ticker = "005930"  # 삼성전자
    s_date, e_date = "20230101", "20230110"
    
    print(f"\nStep 2: 📊 {ticker} 데이터 호출 ({s_date} ~ {e_date})")
    
    # A. 가격 데이터
    df_price = stock.get_market_ohlcv(s_date, e_date, ticker)
    print(f"- 가격 데이터 수집: {len(df_price)}건")

    # B. 공매도 데이터 (생 데이터 확인)
    df_short_raw = stock.get_shorting_balance_by_date(s_date, e_date, ticker)
    
    if df_short_raw.empty:
        print("❌ 공매도 raw 데이터가 비어있습니다! (세션 문제 가능성 99%)")
    else:
        print(f"✅ 공매도 raw 데이터 수집 성공! ({len(df_short_raw)}건)")
        print(f"- 수신된 컬럼명들: {list(df_short_raw.columns)}")
        
        # C. 컬럼 매칭 테스트
        target_cols = ['공매도금액', '공매도잔고금액', '잔고금액']
        found_col = next((c for c in target_cols if c in df_short_raw.columns), None)
        print(f"- 매칭된 컬럼: {found_col}")

        if found_col:
            # D. 데이터 타입 및 조인 테스트
            df_short_val = df_short_raw[[found_col]].rename(columns={found_col: 'Short_Balance'})
            print(f"- 매핑된 데이터 샘플:\n{df_short_val.head(3)}")
            
            # E. 조인 결과 확인
            df_merged = df_price.join(df_short_val)
            print(f"\nStep 3: 🔗 최종 병합 결과 (Short_Balance)")
            print(df_merged[['종가', 'Short_Balance']])
            
            non_null = df_merged['Short_Balance'].notnull().sum()
            if non_null > 0:
                print(f"\n✨ 결론: 수집 성공! ({non_null}건의 공매도 데이터가 존재함)")
            else:
                print("\n🚨 결론: 병합 과정에서 데이터가 사라졌습니다! (인덱스 불일치 의심)")

if __name__ == "__main__":
    debug_fetch()