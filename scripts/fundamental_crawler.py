import os
import re
import time
import pymysql
import requests
import numpy as np
import pandas as pd
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. 설정 및 초기화
# ==========================================
load_dotenv()

BASE_URL = "https://seibro.or.kr"
API_URL = "https://seibro.or.kr/websquare/engine/proworks/callServletService.jsp"
TO_YEAR = 2025
TYPE_ = "연결"

HEADERS = {
    "Content-Type": "application/xml; charset=UTF-8",
    "Accept": "application/xml",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# Seibro API 호출 스펙
REQUESTS = {
    "fin_stmt": {"action":"lsgnInvcList", "menu_no":8,  "w2xpath":"/IPORTAL/user/company/BIP_CNTS01005V.xml", "extra":'<UNIT value="100000000"/>'},
    "ratio":    {"action":"fnafRatioList","menu_no":9,  "w2xpath":"/IPORTAL/user/company/BIP_CNTS01008V.xml", "extra":""},
    "invest":   {"action":"invstIndexList","menu_no":10,"w2xpath":"/IPORTAL/user/company/BIP_CNTS01009V.xml", "extra":""},
}

# DB 컬럼 매핑
HB_TO_COL = {
    "PER(주가수익비율)": "per_raw",
    "PBR(주가순자산비율)": "pbr",
    "EV/EBITDA(기업가치/영업이익 비율)": "ev_ebitda_raw",
    "ROA": "roa",
    "ROE": "roe",
    "매출액증가율": "revenue_growth",
    "조정영업이익률": "operating_margin",
    "영업손익률": "operating_margin",
    "부채비율": "debt_ratio",
    "EBITDA마진율": "ebitda_margin",
    "매출액": "revenue",
    "영업이익": "operating_income",
    "당기순이익(손실)": "net_income",
    "경상개발비": "rnd_expense",
    "감가상각비": "depreciation",
    "EPS(주당순이익)": "eps",
    "단기금융부채": "short_debt",
    "장기금융부채": "long_debt",
    "현금및현금성자산(현금성자산)": "cash",
}

# 재편된 DB 구조에 맞춘 최종 컬럼 리스트
FINAL_DB_COLS = [
    "ticker", "year", "quarter", "revenue", "revenue_growth", 
    "operating_income", "operating_margin", "net_income", 
    "depreciation", "rnd_expense", "roe", "roa", "debt_ratio", 
    "price", "shares", "market_cap", "per", "pbr", "ebitda", "ev_ebitda"
]

# ==========================================
# 2. 유틸리티 및 API 연동
# ==========================================

def _connect():
    return pymysql.connect(
        host=os.environ.get('DB_HOST'),
        port=int(os.environ.get('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

def build_payload(spec, custno):
    return f"""<reqParam action="{spec['action']}" task="ksd.safe.bip.cnts.Company.process.EntrFnafInfoPTask">
<MENU_NO value="{spec['menu_no']}"/>
<W2XPATH value="{spec['w2xpath']}"/>
<ISSUCO_CUSTNO value="{custno}"/>
<TO_YEAR value="{TO_YEAR}"/>
<TYPE value="{TYPE_}"/>
{spec["extra"]}
</reqParam>"""

def get_issuco_custno(session, ticker):
    payload = f'<reqParam action="searchCompanyContentList" task="ksd.safe.bip.cmuc.User.process.SearchPTask"><search_string value="{ticker}"/></reqParam>'
    r = session.post(API_URL, data=payload.encode("utf-8"), headers=HEADERS)
    root = ET.fromstring(r.text)
    for el in root.iter():
        if el.tag.endswith("ISSUCO_CUSTNO"):
            return el.get("value")
    return None

def parse_xml_to_long(xml_text):
    root = ET.fromstring(xml_text)
    rows = []
    for data in root.findall(".//data"):
        result = data.find("result")
        if result is None: continue
        hb_el = result.find("HB")
        if hb_el is None: continue
        account = re.sub(r"<.*?>", "", hb_el.get("value") or "").strip()
        for i in range(1, 21):
            el = result.find(f"A{i}")
            if el is None: continue
            v = el.get("value")
            if v in (None, "", "-"): continue
            try:
                rows.append({"account": account, "A_index": i, "value": float(v.replace(",", ""))})
            except: continue
    return pd.DataFrame(rows)

def make_a_to_period(to_year, years_count=5):
    m = {}
    a = 1
    for y in range(to_year, to_year - years_count, -1):
        m[a] = (y, 0); a+=1 # ANNU (연간)
        m[a] = (y, 4); a+=1 # 4Q
        m[a] = (y, 3); a+=1 # 3Q
        m[a] = (y, 2); a+=1 # 2Q
        m[a] = (y, 1); a+=1 # 1Q
    return m

A_MAP = make_a_to_period(TO_YEAR)

# ==========================================
# 3. 데이터 가공 로직
# ==========================================

def process_raw_data(all_long_df, ticker):
    df = all_long_df.copy()
    # 기간 매핑
    periods = df["A_index"].apply(lambda i: A_MAP.get(int(i), (None, None))).tolist()
    df["year"], df["quarter"] = zip(*periods)
    
    # 분기 데이터만 필터링 (0은 연간 데이터이므로 제외)
    df = df[df["quarter"] > 0].dropna(subset=["year"])
    
    # 계정 매핑
    df = df[df["account"].isin(HB_TO_COL)].copy()
    df["col"] = df["account"].map(HB_TO_COL)
    
    # Pivot
    wide = df.pivot_table(index=["year", "quarter"], columns="col", values="value", aggfunc="first").reset_index()
    
    # 🎯 타입 에러 방지: 모든 수치 컬럼을 숫자형으로 강제 변환
    num_cols = wide.columns.drop(['year', 'quarter'])
    for c in num_cols:
        wide[c] = pd.to_numeric(wide[c], errors="coerce")
    
    # 단위 보정
    money_cols = ["revenue", "operating_income", "net_income", "rnd_expense",
                  "depreciation","short_debt", "long_debt", "cash"]
    pct_cols = ["roa", "roe", "revenue_growth", "operating_margin", "debt_ratio", "ebitda_margin"]
    
    for c in money_cols:
        if c in wide.columns: wide[c] = wide[c] * 100_000_000
    for c in pct_cols:
        if c in wide.columns: wide[c] = wide[c] * 0.01

    # EBITDA 계산
    if "revenue" in wide.columns and "ebitda_margin" in wide.columns:
        wide["ebitda"] = wide["revenue"] * wide["ebitda_margin"]
    
    wide["ticker"] = ticker
    return wide

def add_market_data(df, ticker):
    try:
        listing = fdr.StockListing("KRX")
        shares = listing.loc[listing["Code"] == ticker, "Stocks"].values[0]
        
        start_date = f"{int(df['year'].min())}-01-01"
        price_df = fdr.DataReader(ticker, start_date)
        
        q_end = {1: "-03-31", 2: "-06-30", 3: "-09-30", 4: "-12-31"}
        
        def get_close(row):
            target_date = f"{int(row['year'])}{q_end[int(row['quarter'])]}"
            try:
                return float(price_df.loc[:target_date].iloc[-1]["Close"])
            except: return np.nan

        df["price"] = df.apply(get_close, axis=1)
        df["shares"] = shares
        df["market_cap"] = df["price"] * df["shares"]

        # 🎯 PER 계산 (EPS 우선, 없으면 제공된 per_raw 사용)
        if "eps" in df.columns:
            eps_clean = pd.to_numeric(df["eps"], errors="coerce").replace(0, np.nan)
            df["per"] = df["price"] / eps_clean
        else:
            df["per"] = df.get("per_raw", np.nan)

        # 🎯 EV/EBITDA 정밀 계산 (부채/현금 고려)
        if "ebitda" in df.columns:
            # 💡 [핵심] 컬럼 존재 여부 체크 후 0으로 안전하게 합산
            s_debt = df["short_debt"] if "short_debt" in df.columns else 0
            l_debt = df["long_debt"] if "long_debt" in df.columns else 0
            cash_val = df["cash"] if "cash" in df.columns else 0
            
            ev = df["market_cap"] + s_debt + l_debt - cash_val
            ebitda_clean = pd.to_numeric(df["ebitda"], errors="coerce").replace(0, np.nan)
            df["ev_ebitda"] = ev / ebitda_clean
        else:
            # ebitda 데이터가 없으면 Seibro에서 준 원본 값을 백업으로 사용
            df["ev_ebitda"] = df.get("ev_ebitda_raw", np.nan)

    except Exception as e:
        print(f"  [WARN] Market data fail: {e}")
        for c in ["price", "shares", "market_cap", "per", "ev_ebitda"]:
            if c not in df.columns: df[c] = np.nan
    return df

# ==========================================
# 4. DB 연동 및 멀티스레딩 실행
# ==========================================

def get_targets_from_db():
    conn = _connect()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE is_active = TRUE;")
            return cur.fetchall()
    finally: conn.close()

def send_to_db(df):
    if df.empty: return
    conn = _connect()
    try:
        cur = conn.cursor()
        df = df.replace({np.nan: None})
        
        # SQL 구문 자동 생성
        cols = [c for c in FINAL_DB_COLS if c in df.columns]
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join([f"{c}=VALUES({c})" for c in cols if c not in ["ticker", "year", "quarter"]])
        
        sql = f"""
            INSERT INTO FUNDAMENTAL_TB ({", ".join(cols)}) 
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
        """
        data = [tuple(row) for row in df[cols].values]
        cur.executemany(sql, data)
        conn.commit()
    except Exception as e:
        print(f"❌ DB 적재 에러: {e}"); conn.rollback()
    finally: conn.close()

def fetch_single_ticker(ticker_info):
    ticker = ticker_info['ticker']
    name = ticker_info['stock_name']

    s = requests.Session()
    try:
        s.get(BASE_URL, headers=HEADERS, timeout=10)
        custno = get_issuco_custno(s, ticker)
        if not custno: return None

        all_long = []
        for spec in REQUESTS.values():
            time.sleep(0.3)
            xml = s.post(API_URL, data=build_payload(spec, custno).encode("utf-8"), headers=HEADERS, timeout=15).text
            all_long.append(parse_xml_to_long(xml))
        
        combined_long = pd.concat(all_long, ignore_index=True)
        panel = process_raw_data(combined_long, ticker)
        panel = add_market_data(panel, ticker)
        
        for c in FINAL_DB_COLS:
            if c not in panel.columns: panel[c] = np.nan
        
        print(f"  [OK] {name}({ticker}) 수집 완료")
        return panel[FINAL_DB_COLS]
    except Exception as e:
        print(f"  [ERROR] {ticker}: {e}")
        return None
    finally:
        s.close()

def run_fundamental_crawler(max_workers=3):
    """멀티스레딩 기반 크롤러 메인"""
    targets = get_targets_from_db()
    
    def get_session():
        s = requests.Session()
        s.get(BASE_URL)
        return s

    batch_results = []
    print(f"🚀 멀티스레딩 크롤링 시작 (Worker: {max_workers})...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single_ticker, t): t for t in targets}
        
        count = 0
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                batch_results.append(result)
            
            count += 1
            # 10종목마다 DB 중간 저장 (안전성)
            if len(batch_results) >= 10:
                send_to_db(pd.concat(batch_results, ignore_index=True))
                batch_results = []
                print(f"--- 중간 적재 완료 ({count}/{len(targets)}) ---")

    # 남은 데이터 저장
    if batch_results:
        send_to_db(pd.concat(batch_results, ignore_index=True))
    
    print("✅ 모든 종목 수집 및 적재 완료")

if __name__ == "__main__":
    run_fundamental_crawler(max_workers=3)