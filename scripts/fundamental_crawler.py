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

# ==========================================
# 1. 설정 및 초기화
# ==========================================
load_dotenv()

BASE_URL = "https://seibro.or.kr"
API_URL = "https://seibro.or.kr/websquare/engine/proworks/callServletService.jsp"
TO_YEAR = datetime.now().year
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
    "PER(주가수익비율)": "per",
    "PBR(주가순자산비율)": "pbr",
    "EV/EBITDA(기업가치/영업이익 비율)": "ev_ebitda",
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

def process_raw_data(all_long_df, ticker, name):
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
    
    # 단위 보정
    money_cols = ["revenue", "operating_income", "net_income", "rnd_expense", "depreciation"]
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
    except Exception as e:
        print(f"  [WARN] Market data fail: {e}")
        for c in ["price", "shares", "market_cap"]: df[c] = np.nan
    return df

# ==========================================
# 4. DB 연동 및 실행
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

def run_fundamental_crawler(chunk_size=10):
    targets = get_targets_from_db()
    session = requests.Session()
    session.get(BASE_URL)

    for i in range(0, len(targets), chunk_size):
        batch = targets[i : i + chunk_size]
        batch_results = []
        
        for t in batch:
            ticker, name = t['ticker'], t['stock_name']
            print(f"▶ [{i//chunk_size + 1}] {name}({ticker}) 분석 중...")
            try:
                custno = get_issuco_custno(session, ticker)
                if not custno: continue

                all_long = []
                for spec in REQUESTS.values():
                    xml = session.post(API_URL, data=build_payload(spec, custno).encode("utf-8"), headers=HEADERS).text
                    all_long.append(parse_xml_to_long(xml))
                
                combined_long = pd.concat(all_long, ignore_index=True)
                panel = process_raw_data(combined_long, ticker, name)
                panel = add_market_data(panel, ticker)
                
                # 최종 컬럼 보정
                for c in FINAL_DB_COLS:
                    if c not in panel.columns: panel[c] = np.nan
                
                batch_results.append(panel[FINAL_DB_COLS])
                time.sleep(0.5) # 과도한 요청 방지
            except Exception as e:
                print(f"  [ERROR] {ticker}: {e}")

        if batch_results:
            send_to_db(pd.concat(batch_results, ignore_index=True))
            print(f"✅ Batch {i//chunk_size + 1} 적재 완료")

if __name__ == "__main__":
    run_fundamental_crawler()