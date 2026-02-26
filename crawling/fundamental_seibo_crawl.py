import re
import os
import numpy as np
import pandas as pd
import requests
import FinanceDataReader as fdr
import xml.etree.ElementTree as ET


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

REQUESTS = {
    "fin_stmt": {"action":"lsgnInvcList", "menu_no":8,  "w2xpath":"/IPORTAL/user/company/BIP_CNTS01005V.xml", "extra":'<UNIT value="100000000"/>'},
    "ratio":    {"action":"fnafRatioList","menu_no":9,  "w2xpath":"/IPORTAL/user/company/BIP_CNTS01008V.xml", "extra":""},
    "invest":   {"action":"invstIndexList","menu_no":10,"w2xpath":"/IPORTAL/user/company/BIP_CNTS01009V.xml", "extra":""},
}

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
    "경상개발비": "rnd",
    "감가상각비": "depreciation",
    "EPS(주당순이익)": "eps",
    "단기금융부채": "short_debt",
    "장기금융부채": "long_debt",
    "현금및현금성자산(현금성자산)": "cash",

}

FINAL_COLS = [
    "기업종목코드","종목명","year","quarter",
    "revenue","revenue_growth","operating_income","operating_margin",
    "net_income","depreciation","rnd",
    "roe","roa","debt_ratio",
    "price","shares","market_cap",
    "per","pbr","ebitda","ev_ebitda"
]


def build_payload(spec, custno):
    return f"""<reqParam action="{spec['action']}" task="ksd.safe.bip.cnts.Company.process.EntrFnafInfoPTask">
<MENU_NO value="{spec['menu_no']}"/>
<CMM_BTN_ABBR_NM value="total_search,openall,print,hwp,word,pdf,searchIcon,seach,"/>
<W2XPATH value="{spec['w2xpath']}"/>
<ISSUCO_CUSTNO value="{custno}"/>
<TO_YEAR value="{TO_YEAR}"/>
<TYPE value="{TYPE_}"/>
{spec["extra"]}
</reqParam>"""

def fetch_xml(session, payload):
    r = session.post(API_URL, data=payload.encode("utf-8"), headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def get_issuco_custno(session, ticker):
    payload = f"""
    <reqParam action="searchCompanyContentList"
              task="ksd.safe.bip.cmuc.User.process.SearchPTask">
        <IS_FF value=""/>
        <search_string value="{ticker}"/>
    </reqParam>
    """

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
        if result is None:
            continue

        hb_el = result.find("HB")
        if hb_el is None:
            continue

        account = hb_el.get("value") or ""
        account = re.sub(r"<.*?>", "", account).strip()

        for i in range(1, 21):
            el = result.find(f"A{i}")
            if el is None:
                continue
            v = el.get("value")
            if v in (None, "", "-"):
                continue
            v = v.replace(",", "")
            try:
                v = float(v)
            except:
                continue
            rows.append({"account": account, "A_index": i, "value": v})
    return pd.DataFrame(rows, columns=["account", "A_index", "value"])

def make_a_to_period(to_year=2025, years=4):
    # A1..A20 = [ANNU, 4Q,3Q,2Q,1Q] * years (to_year부터 역순)
    m = {}
    a = 1
    for y in range(to_year, to_year - years, -1):
        m[a] = (y,"ANNU"); a+=1
        m[a] = (y,"4Q");   a+=1
        m[a] = (y,"3Q");   a+=1
        m[a] = (y,"2Q");   a+=1
        m[a] = (y,"1Q");   a+=1
    return m

A_TO_PERIOD = make_a_to_period(TO_YEAR, 4)

def apply_units(wide: pd.DataFrame) -> pd.DataFrame:
    # money: fin_stmt가 <UNIT value="100000000"/>라서 억원 단위 -> 원으로 (x 1e8)
    money_cols = ["revenue","operating_income","net_income","rnd","depreciation","short_debt","long_debt","cash"]
    for c in money_cols:
        if c in wide.columns:
            wide[c] = pd.to_numeric(wide[c], errors="coerce") * 100_000_000

    # percent: ratio/invest 쪽은 보통 % -> 비율로 (x 0.01)
    pct_cols = ["roa","roe","revenue_growth","operating_margin","debt_ratio","ebitda_margin"]
    for c in pct_cols:
        if c in wide.columns:
            wide[c] = pd.to_numeric(wide[c], errors="coerce") * 0.01

    # EBITDA 재계산 (ebitda_margin이 비율(0~1)이 된 이후)
    if "revenue" in wide.columns and "ebitda_margin" in wide.columns:
        wide["ebitda"] = wide["revenue"] * wide["ebitda_margin"]

    return wide

def add_market_data(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()

    quarter_end_map = {1: "-03-31", 2: "-06-30", 3: "-09-30", 4: "-12-31"}
    ticker = panel["기업종목코드"].iloc[0]

    start_year = int(panel["year"].min())
    end_year   = int(panel["year"].max())

    price_df = fdr.DataReader(ticker, f"{start_year}-01-01", f"{end_year}-12-31")

    listing = fdr.StockListing("KRX")
    shares_row = listing[listing["Code"] == ticker]
    shares = shares_row["Stocks"].values[0] if len(shares_row) > 0 else np.nan

    prices, market_caps = [], []
    for _, row in panel.iterrows():
        q = int(row["quarter"])
        date_str = f"{int(row['year'])}{quarter_end_map.get(q, '-12-31')}"
        temp = price_df.loc[:date_str]
        close_price = float(temp.iloc[-1]["Close"]) if len(temp) > 0 else np.nan

        prices.append(close_price)
        market_caps.append(close_price * shares if pd.notna(close_price) and pd.notna(shares) else np.nan)

    panel["price"] = prices
    panel["shares"] = shares
    panel["market_cap"] = market_caps

    # --- PER (EPS 기반) ---
    if "eps" in panel.columns:
        eps = pd.to_numeric(panel["eps"], errors="coerce").replace(0, np.nan)
        panel["per"] = panel["price"] / eps

    # --- EV / EBITDA ---
    if "ebitda" in panel.columns:
        short_debt = pd.to_numeric(panel["short_debt"], errors="coerce") if "short_debt" in panel.columns else pd.Series(np.nan, index=panel.index)
        long_debt  = pd.to_numeric(panel["long_debt"],  errors="coerce") if "long_debt"  in panel.columns else pd.Series(np.nan, index=panel.index)
        cash       = pd.to_numeric(panel["cash"],       errors="coerce") if "cash"       in panel.columns else pd.Series(np.nan, index=panel.index)

        ev = panel["market_cap"] + short_debt.fillna(0) + long_debt.fillna(0) - cash.fillna(0)
        panel["ev_ebitda"] = ev / pd.to_numeric(panel["ebitda"], errors="coerce").replace(0, np.nan)

    panel = panel.drop(columns=["eps", "short_debt", "long_debt", "cash"], errors="ignore")
    return panel

def build_quarter_panel(df_long, ticker, name):
    df = df_long.copy()

    # A_index -> (year, quarter)
    df[["year","quarter"]] = df["A_index"].apply(lambda i: A_TO_PERIOD.get(int(i),(None,None))).tolist()
    df = df[df["quarter"].isin(["1Q","2Q","3Q","4Q"])].dropna(subset=["year","quarter"])
    df["year"] = df["year"].astype(int)

    # HB 정확매칭 + 컬럼명 매핑
    df = df[df["account"].isin(HB_TO_COL)].copy()
    df["col"] = df["account"].map(HB_TO_COL)

    # wide (year, reprt_code 기준)
    wide = df.pivot_table(
        index=["year","quarter"],
        columns="col",
        values="value",
        aggfunc="first"
    ).reset_index()

    wide["quarter"] = wide["quarter"].str.replace("Q","").astype(int)
    wide = apply_units(wide)

    # 메타
    wide["기업종목코드"] = ticker
    wide["종목명"] = name

    # 중간 컬럼 제거
    if "ebitda_margin" in wide.columns:
        wide = wide.drop(columns=["ebitda_margin"])

    # 없는 컬럼 NaN 채우기
    for c in FINAL_COLS:
        if c not in wide.columns:
            wide[c] = np.nan

    temp_cols = ["eps", "short_debt", "long_debt", "cash"]
    keep_cols = list(dict.fromkeys(FINAL_COLS + [c for c in temp_cols if c in wide.columns]))

    return wide[keep_cols].sort_values(["year","quarter"]).reset_index(drop=True)

def run(csv_path, out_file="fin_all.csv"):
    df = pd.read_csv(csv_path, dtype=str)

    s = requests.Session()
    s.get(BASE_URL)

    for _, row in df.iterrows():
        ticker = str(row["기업종목코드"]).zfill(6)
        name = str(row["종목명"])

        try:
            custno = get_issuco_custno(s, ticker)
            if custno is None:
                print("[SKIP] 회사코드 못 찾음:", ticker, name)
                continue

            all_long = []
            for spec in REQUESTS.values():
                xml = fetch_xml(s, build_payload(spec, custno))
                long_df = parse_xml_to_long(xml)
                if long_df is not None and len(long_df) > 0:
                    all_long.append(long_df)

            if len(all_long) == 0:
                print("[SKIP] 파싱 데이터 없음:", ticker, name)
                continue

            df_long_all = pd.concat(all_long, ignore_index=True)
            panel = build_quarter_panel(df_long_all, ticker, name)

            if panel is None or len(panel) == 0:
                print("[SKIP] 분기 패널 비어있음:", ticker, name)
                continue

            # market data는 실패해도 재무는 저장되게
            try:
                panel = add_market_data(panel)
            except Exception as e:
                print("[WARN] market data 실패:", ticker, name, "|", e)
                if "price" not in panel.columns: panel["price"] = np.nan
                if "shares" not in panel.columns: panel["shares"] = np.nan
                if "market_cap" not in panel.columns: panel["market_cap"] = np.nan

            if os.path.exists(out_file):
                old = pd.read_csv(out_file, dtype={"기업종목코드": str})
                panel = pd.concat([old, panel], ignore_index=True)

            panel = panel.drop_duplicates(["기업종목코드","year","quarter"], keep="last")
            panel = panel.drop(columns=["eps"], errors="ignore")
            panel.to_csv(out_file, index=False, encoding="utf-8-sig")
            print("[OK] 저장:", ticker, name, "| total_rows =", len(panel))

        except Exception as e:
            print("[FAIL] 기업 처리 실패:", ticker, name, "|", e)
            continue

    print("[DONE] 최종 저장 완료 ->", out_file)
    return out_file

run("KOSPI200.csv", "fin_all.csv")