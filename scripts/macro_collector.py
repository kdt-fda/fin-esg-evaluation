import os
import requests
import pandas as pd
import numpy as np
import pymysql
from datetime import datetime, timedelta
from dotenv import load_dotenv
import warnings

warnings.filterwarnings('ignore')
load_dotenv()

# ==========================================
# 1. 설정 및 API 키
# ==========================================
ECOS_API_KEY = os.getenv("ECOS_API_KEY")
FRED_API_KEY = os.getenv("FRED_API_KEY")

def _connect():
    host = os.environ.get('DB_HOST')
    port = int(os.environ.get('DB_PORT'))
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name
    )

    return conn

FINAL_CUT_START = "2023-01-01"

# ==========================================
# 2. 수집 유틸리티 (팀원 로직 원본 유지)
# ==========================================
def _get_json(url):
    r = requests.get(url, timeout=30); r.raise_for_status()
    return r.json()

def ecos_fetch(stat, item, cycle, start, end, colname):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr/1/1000/{stat}/{cycle}/{start}/{end}/{item}"
    j = _get_json(url)
    if "StatisticSearch" not in j: return pd.DataFrame()
    df = pd.DataFrame(j["StatisticSearch"]["row"])[["TIME", "DATA_VALUE"]]
    if cycle == "Q": df["date"] = pd.PeriodIndex(df["TIME"], freq="Q").to_timestamp()
    elif cycle == "M": df["date"] = pd.to_datetime(df["TIME"], format="%Y%m")
    else: df["date"] = pd.to_datetime(df["TIME"], format="%Y%m%d")
    df[colname] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    return df[["date", colname]]

def fetch_fred_series(series_id, colname, start_date):
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json", "observation_start": start_date}
    r = requests.get(url, params=params); r.raise_for_status()
    df = pd.DataFrame(r.json()["observations"])[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df[colname] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", colname]]

# ==========================================
# 3. 메인 실행 파이프라인 (병합 및 전처리 통합)
# ==========================================
def run_macro_collector(is_initial=False):
    # 수집 기간 설정
    if is_initial:
        s_d, s_m, s_q, s_fred = "20220101", "202201", "2021Q1", "2022-01-01"
        trade_s_m = "202101"
    else:
        lookback = (datetime.now() - timedelta(days=60))
        s_d, s_m, s_fred = lookback.strftime("%Y%m%d"), lookback.strftime("%Y%m"), lookback.strftime("%Y-%m-%d")
        s_q = (datetime.now() - timedelta(days=200)).strftime("%YQ1")
        trade_s_m = (datetime.now() - timedelta(days=500)).strftime("%Y%m")

    e_d = datetime.now().strftime("%Y%m%d")
    e_m = datetime.now().strftime("%Y%m")
    e_q = "2025Q4"

    dfs = {}

    # 데이터 수집 (ECOS)
    daily_vars = [("ktb3y", "817Y002", "010200000"), ("ktb10y", "817Y002", "010210000"), 
                  ("usdkrw", "731Y003", "0000003"), ("base_rate", "722Y001", "0101000")]
    for name, stat, item in daily_vars:
        dfs[name] = ecos_fetch(stat, item, "D", s_d, e_d, name)

    monthly_vars = [("wti", "902Y003", "010101"), ("brent", "902Y003", "010103"), 
                    ("kr_cpi", "901Y009", "0"), ("unemployment_rate", "901Y027", "I61BC"), 
                    ("ccsi", "511Y002", "FME")]
    for name, stat, item in monthly_vars:
        dfs[name] = ecos_fetch(stat, item, "M", s_m, e_m, name)

    # 수출입 YoY (계산 로직 통합)
    for mode, stat_code in [("export", "T002"), ("import", "T004")]:
        raw = ecos_fetch("901Y119", stat_code, "M", trade_s_m, e_m, f"{mode}_total")
        if not raw.empty:
            df_trade = raw.groupby("date")[f"{mode}_total"].sum().reset_index().sort_values("date")
            df_trade[f"{mode}_yoy"] = df_trade[f"{mode}_total"].pct_change(12) * 100
            dfs[mode] = df_trade[["date", f"{mode}_yoy"]]

    # GDP QoQ
    gdp_df = ecos_fetch("200Y108", "10601", "Q", s_q, e_q, "gdp_level")
    if not gdp_df.empty:
        gdp_df["gdp_qoq"] = (gdp_df["gdp_level"] / gdp_df["gdp_level"].shift(1) - 1) * 100
        dfs["gdp"] = gdp_df

    # 데이터 수집 (FRED)
    fred_vars = {"us_cpi": "CPIAUCSL", "us_core_cpi": "CPILFESL", "us_core_pce": "PCEPILFE",
                 "us_unrate": "UNRATE", "us_init_claims": "ICSA", "us_policy_rate": "EFFR",
                 "us_ust_3y": "DGS3", "us_ust_10y": "DGS10", "jpy3": "IR3TIB01JPM156N",
                 "jpy10": "IRLTLT01JPM156N", "pmi": "IPMAN"}
    for col, sid in fred_vars.items():
        dfs[col] = fetch_fred_series(sid, col, s_fred)

    # 통합 및 전처리
    valid_dfs = [v for v in dfs.values() if v is not None and not v.empty]
    merged = valid_dfs[0]
    for d in valid_dfs[1:]:
        merged = pd.merge(merged, d, on="date", how="outer")

    merged = merged.sort_values("date")

    # 결측치 채우기 (이미 계산된 YoY 등을 오늘 날짜까지 확장)
    all_cols = [c for c in merged.columns if c != 'date']
    merged[all_cols] = merged[all_cols].ffill().bfill()

    # 파생 변수 계산
    merged["rate_diff_policy"] = merged["us_policy_rate"] - merged["base_rate"]
    merged["rate_diff_3y"] = merged["us_ust_3y"] - merged["ktb3y"]
    merged["rate_diff_10y"] = merged["us_ust_10y"] - merged["ktb10y"]

    # 최종 필터링 및 컬럼명 통일
    merged = merged[merged["date"] >= FINAL_CUT_START].reset_index(drop=True)
    merged = merged.rename(columns={'date': 'trade_date'})

    # DB 적재
    if not merged.empty:
        send_to_macro_db(merged)

# ==========================================
# 4. DB 적재 (MACROECONOMICS_TB)
# ==========================================
def send_to_macro_db(df):
    conn = _connect()
    
    try:
        cur = conn.cursor()
        df = df.replace({np.nan: None})
        
        cols = ["trade_date"] + [c for c in df.columns if c != 'date']
        placeholders = ", ".join(["%s"] * len(cols))
        update_stmt = ", ".join([f"{c}=VALUES({c})" for c in cols[1:]])
        
        sql = f"INSERT INTO MACROECONOMICS_TB ({', '.join(cols)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_stmt};"
        cur.executemany(sql, [tuple(row) for row in df.values])
        conn.commit()
        print(f"✅ 거시경제 지표 통합 적재 완료 (총 {len(df)}행)")
    finally: conn.close()

if __name__ == "__main__":
    run_macro_collector(is_initial=False)