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

DB_CONFIG = {
    'host': '52.79.234.231', 'port': 3302, 'user': 'root',
    'password': 'team2', 'database': 'STOCK_DB', 'charset': 'utf8mb4'
}

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
    if is_initial:
        s_d, s_m, s_q, s_fred = "20230101", "202301", "2022Q4", "2023-01-01"
    else:
        lookback = (datetime.now() - timedelta(days=15))
        s_d, s_m, s_fred = lookback.strftime("%Y%m%d"), lookback.strftime("%Y%m"), lookback.strftime("%Y-%m-%d")
        s_q = (datetime.now() - timedelta(days=120)).strftime("%YQ1")

    e_d, e_m = datetime.now().strftime("%Y%m%d"), datetime.now().strftime("%Y%m")
    dfs = []

    # 3-1) ECOS 수집
    ecos_vars = [
        ("ktb3y", "817Y002", "010200000", "D"), ("ktb10y", "817Y002", "010210000", "D"),
        ("usdkrw", "731Y003", "0000003", "D"), ("base_rate", "722Y001", "0101000", "D"),
        ("kr_cpi", "901Y009", "0", "M"), ("unemployment_rate", "901Y027", "I61BC", "M"),
        ("ccsi", "511Y002", "FME", "M"), ("wti", "902Y003", "010101", "M"),
        ("brent", "902Y003", "010103", "M"), ("gdp_level", "200Y108", "10601", "Q")
    ]
    for name, stat, item, cycle in ecos_vars:
        dfs.append(ecos_fetch(stat, item, cycle, s_d if cycle=="D" else s_m if cycle=="M" else s_q, e_d, name))

    # 3-2) FRED 수집 (일본 금리 jpy3, jpy10 및 PMI 포함)
    fred_vars = {
        "us_cpi": "CPIAUCSL", "us_core_cpi": "CPILFESL", "us_core_pce": "PCEPILFE",
        "us_unrate": "UNRATE", "us_init_claims": "ICSA", "us_policy_rate": "EFFR",
        "us_ust_3y": "DGS3", "us_ust_10y": "DGS10",
        "jpy3": "INTGSTJPM193N", "jpy10": "IRLTLT01JPM156N", "pmi": "MANPMI01USM661S"
    }
    for col, sid in fred_vars.items():
        try: dfs.append(fetch_fred_series(sid, col, s_fred))
        except: print(f"⚠️ FRED SKIP: {col}")

    # 3-3) 데이터 병합 (Outer Merge)
    df_merged = dfs[0]
    for next_df in dfs[1:]:
        if next_df.empty: continue
        df_merged = pd.merge(df_merged, next_df, on="date", how="outer")
    
    df_merged = df_merged.sort_values("date").reset_index(drop=True)

    # 3-4) 컬럼 성격별 전처리 (팀원 코드 로직 4번 반영)
    # (1) 월별/분기별 상태 변수 -> ffill
    monthly_cols = ["us_cpi", "us_core_cpi", "us_core_pce", "us_unrate", "kr_cpi", "unemployment_rate", "ccsi", "gdp_level", "wti", "brent", "pmi"]
    monthly_cols = [c for c in monthly_cols if c in df_merged.columns]
    df_merged[monthly_cols] = df_merged[monthly_cols].ffill()

    # (2) 금융시장 변수(평일/휴일) -> ffill 후 bfill
    market_cols = ["us_policy_rate", "us_ust_3y", "us_ust_10y", "ktb3y", "ktb10y", "usdkrw", "jpy3", "jpy10", "base_rate", "us_init_claims"]
    market_cols = [c for c in market_cols if c in df_merged.columns]
    df_merged[market_cols] = df_merged[market_cols].ffill().bfill()

    # 3-5) 파생 변수 계산 (팀원 코드 로직 6번 반영)
    if "gdp_level" in df_merged.columns:
        df_merged["gdp_qoq"] = (df_merged["gdp_level"] / df_merged["gdp_level"].shift(1) - 1) * 100
    
    if {"us_policy_rate", "base_rate"}.issubset(df_merged.columns):
        df_merged["rate_diff_policy"] = df_merged["us_policy_rate"] - df_merged["base_rate"]
    
    if {"us_ust_3y", "ktb3y"}.issubset(df_merged.columns):
        df_merged["rate_diff_3y"] = df_merged["us_ust_3y"] - df_merged["ktb3y"]
    
    if {"us_ust_10y", "ktb10y"}.issubset(df_merged.columns):
        df_merged["rate_diff_10y"] = df_merged["us_ust_10y"] - df_merged["ktb10y"]

    # 3-6) 분석 시점 컷 및 DB 적재
    df_merged = df_merged[df_merged["date"] >= FINAL_CUT_START].reset_index(drop=True)
    send_to_macro_db(df_merged)

# ==========================================
# 4. DB 적재 (MACROECONOMICS_TB)
# ==========================================
def send_to_macro_db(df):
    conn = pymysql.connect(**DB_CONFIG)
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
    run_macro_collector(is_initial=True)