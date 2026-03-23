import os
import requests
import pandas as pd
import pymysql
from datetime import datetime, timedelta
from dotenv import load_dotenv
import warnings
import FinanceDataReader as fdr

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
# 2. 수집 유틸리티
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

def fetch_market_data(ticker, colname, start_date):
    try:
        df = fdr.DataReader(ticker, start_date)
        if df.empty:
            print(f"⚠️ {ticker} 데이터를 가져오지 못했습니다.")
            return pd.DataFrame()
        
        df.index.name = 'date'
        df = df.reset_index()
        df = df[['date', 'Close']].rename(columns={'Close': colname})
        return df
    except Exception as e:
        print(f"⚠️ 시장 데이터 수집 에러 ({ticker}): {e}")
        return pd.DataFrame()

# ==========================================
# 3. 메인 실행 파이프라인
# ==========================================
def run_macro_collector(is_initial=False):
    # 수집 기간 설정
    if is_initial:
        s_d, s_m, s_q, s_fred = "20220101", "202201", "2021Q1", "2022-01-01"
        trade_s_m = "202101"
    else:
        lookback = (datetime.now() - timedelta(days=90))
        s_d, s_m, s_fred = lookback.strftime("%Y%m%d"), lookback.strftime("%Y%m"), lookback.strftime("%Y-%m-%d")
        s_q = (datetime.now() - timedelta(days=365)).strftime("%YQ1")
        trade_s_m = (datetime.now() - timedelta(days=500)).strftime("%Y%m")

    e_d = datetime.now().strftime("%Y%m%d")
    e_m = datetime.now().strftime("%Y%m")
    e_q = f"{datetime.now().year}Q{(datetime.now().month - 1) // 3 + 1}"

    dfs = {}

    # 데이터 수집 (ECOS)
    daily_vars = [("ktb3y", "817Y002", "010200000"), ("ktb10y", "817Y002", "010210000"), 
                  ("usdkrw", "731Y003", "0000003"), ("base_rate", "722Y001", "0101000")]
    for name, stat, item in daily_vars:
        dfs[name] = ecos_fetch(stat, item, "D", s_d, e_d, name)

    monthly_vars = [("kr_cpi", "901Y009", "0"), ("unemployment_rate", "901Y027", "I61BC"), 
                    ("ccsi", "511Y002", "FME")]
    for name, stat, item in monthly_vars:
        dfs[name] = ecos_fetch(stat, item, "M", s_m, e_m, name)

    # 수출입 YoY
    for mode, stat_code in [("export", "T002"), ("import", "T004")]:
        raw = ecos_fetch("901Y119", stat_code, "M", trade_s_m, e_m, f"{mode}_total")
        if not raw.empty:
            df_trade = raw.groupby("date")[f"{mode}_total"].sum().reset_index().sort_values("date")
            df_trade[f"{mode}_yoy"] = df_trade[f"{mode}_total"].pct_change(12) * 100
            dfs[mode] = df_trade[["date", f"{mode}_total", f"{mode}_yoy"]]

    # GDP QoQ
    gdp_df = ecos_fetch("200Y108", "10601", "Q", s_q, e_q, "gdp_level")
    if not gdp_df.empty:
        gdp_df["gdp_qoq"] = (gdp_df["gdp_level"] / gdp_df["gdp_level"].shift(1) - 1) * 100
        dfs["gdp"] = gdp_df[["date", "gdp_level", "gdp_qoq"]]

    # FRED 데이터
    fred_vars = {"us_cpi": "CPIAUCSL", "us_core_cpi": "CPILFESL", "us_core_pce": "PCEPILFE",
                 "us_unrate": "UNRATE", "us_init_claims": "ICSA", "us_policy_rate": "EFFR",
                 "us_ust_3y": "DGS3", "us_ust_10y": "DGS10", "jpy3": "IR3TIB01JPM156N",
                 "jpy10": "IRLTLT01JPM156N", "pmi": "IPMAN"}
    for col, sid in fred_vars.items():
        dfs[col] = fetch_fred_series(sid, col, s_fred)

    # 유가(WTI, Brent)
    market_vars = {"wti": "CL=F", "brent": "BZ=F"} # CL=F: WTI 선물, BZ=F: 브렌트유 선물
    for col, ticker in market_vars.items():
        dfs[col] = fetch_market_data(ticker, col, s_fred)

    # 통합 및 결측치 방어
    valid_dfs = [v for v in dfs.values() if v is not None and not v.empty]
    if not valid_dfs:
        print("❌ 수집된 데이터가 하나도 없습니다.")
        return
    
    # 기준 날짜축 생성 (FINAL_CUT_START ~ 오늘)
    date_spine = pd.date_range(start=FINAL_CUT_START, end=datetime.now(), freq='D')
    merged = pd.DataFrame({'date': date_spine})

    # 순차 병합
    for d in valid_dfs:
        d['date'] = pd.to_datetime(d['date']).dt.normalize()
        d = d.drop_duplicates('date')
        merged = pd.merge(merged, d, on="date", how="left")

    merged = merged.sort_values("date")

    # 지표별 최신 공시 현황 리포트 및 ffill
    print("\n--- [지표별 최신 데이터 현황] ---")
    all_cols = [c for c in merged.columns if c != 'date']
    for col in all_cols:
        last_date = merged[merged[col].notnull()]['date'].max()
        if pd.isna(last_date):
            print(f"⚠️ {col:20}: 데이터 없음")
        else:
            delay = (datetime.now() - last_date).days
            status = "✅ 정상" if delay < 40 else "⏳ 발표지연"
            print(f"{status} {col:20}: {last_date.strftime('%Y-%m-%d')} ({delay}일전)")

    # 결측치 처리
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

        # 컬럼 순서 확인
        cur.execute("DESCRIBE MACROECONOMICS_TB")
        db_cols = [row[0] for row in cur.fetchall()]

        for col in db_cols:
            if col not in df.columns:
                df[col] = None

        df_db = df[db_cols]
        df_db = df_db.where(pd.notnull(df_db), None)
        
        placeholders = ", ".join(["%s"] * len(db_cols))
        update_stmt = ", ".join([f"{c}=VALUES({c})" for c in db_cols if c != 'trade_date'])

        sql = f"""
            INSERT INTO MACROECONOMICS_TB ({', '.join(db_cols)}) 
            VALUES ({placeholders}) 
            ON DUPLICATE KEY UPDATE {update_stmt};
        """

        cur.executemany(sql, [tuple(row) for row in df_db.values])
        conn.commit()
        print(f"✅ MACROECONOMICS_TB 적재 완료 {len(df_db)}행 (최신일: {df_db['trade_date'].max()})")
    except Exception as e:
        print(f"❌ DB 적재 에러: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_macro_collector(is_initial=False)