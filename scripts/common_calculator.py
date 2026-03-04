import os
import requests
import pymysql
import numpy as np
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# ============================================================
# 1. 설정 및 초기화
# ============================================================
load_dotenv()

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

FETCH_START_DATE = '2021-01-01'
FINAL_START_DATE = '2023-01-01'
LAG_MONTHS = (1, 3, 6)

def fetch_kospi200_naver(start_date):
    print(f"📡 코스피200 수집 중 (네이버 금융 직접 추출)...")
    url = 'https://finance.naver.com/sise/sise_index_day.naver?code=KPI200&page=1'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        df_list = pd.read_html(response.text)
        df = df_list[0].dropna()
        
        df = df[['날짜', '체결가']]
        df.columns = ['trade_date', 'close_kospi200']
        
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.normalize()
        
        df = df[df['trade_date'] >= pd.to_datetime(start_date)]
        return df.sort_values('trade_date')
    except Exception as e:
        print(f"❌ 네이버 수집 에러: {e}")
        return pd.DataFrame()

# ============================================================
# 2. ECOS Client (선행지수 수집)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ECOS_API_KEY")
        self.session = requests.Session()

    def fetch_cli_data(self, start, end):
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/1000/901Y067/M/{start}/{end}/I16E"
        try:
            resp = self.session.get(url, timeout=30)
            rows = resp.json().get("StatisticSearch", {}).get("row", [])
            if not rows: return pd.DataFrame(columns=["trade_date", "cli"])
            
            df = pd.DataFrame(rows)
            df["trade_date"] = pd.to_datetime(df["TIME"], format="%Y%m").dt.normalize()
            df["cli"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
            return df[["trade_date", "cli"]]
        except Exception as e:
            print(f"📡 ECOS API 오류: {e}")
            return pd.DataFrame(columns=["trade_date", "cli"])

# ============================================================
# 3. 지표 계산 및 병합
# ============================================================
def calculate_common_indicators(df_kospi, cli_raw):
    df = df_kospi.copy().sort_values("trade_date")
    
    # 1) 주가 기반 레짐 지표
    df['ma200'] = df['close_kospi200'].rolling(window=200, min_periods=100).mean()
    df['bull_dummy'] = (df['close_kospi200'] > df['ma200']).astype(int)
    df['mkt_ret'] = df['close_kospi200'].pct_change()
    df['mkt_vol_20'] = df['mkt_ret'].rolling(window=20, min_periods=20).std()
    df['vol_threshold'] = df['mkt_vol_20'].rolling(window=252, min_periods=100).quantile(0.8)
    df['high_vol_dummy'] = (df['mkt_vol_20'] > df['vol_threshold']).astype(int)
    df['mkt_regime'] = df['bull_dummy'] * 2 + df['high_vol_dummy']

    # 2) CLI 및 Lag 지표
    cli_df = cli_raw.sort_values("trade_date").reset_index(drop=True)
    for k in LAG_MONTHS:
        cli_df[f"cli_lag{k}"] = cli_df["cli"].shift(k)

    # 3) 병합
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    cli_df['trade_date'] = pd.to_datetime(cli_df['trade_date'])
    
    merged = pd.merge_asof(df, cli_df, on="trade_date", direction="backward")
    cli_cols = ['cli', 'cli_lag1', 'cli_lag3', 'cli_lag6']
    merged[cli_cols] = merged[cli_cols].ffill()
    
    return merged[merged["trade_date"] >= FINAL_START_DATE]

# ============================================================
# 4. DB 적재 (INSERT 전용)
# ============================================================
def send_to_common_db(df):
    if df.empty: return

    conn = _connect()
    
    try:
        cur = conn.cursor()
        df = df.replace({np.nan: None})
        
        sql = """
            INSERT INTO COMMON_TB (
                trade_date, close_kospi200, ma200, bull_dummy, mkt_ret, 
                mkt_vol_20, vol_threshold, high_vol_dummy, mkt_regime, 
                cli, cli_lag1, cli_lag3, cli_lag6
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                close_kospi200=VALUES(close_kospi200),
                ma200=VALUES(ma200),
                bull_dummy=VALUES(bull_dummy),
                mkt_ret=VALUES(mkt_ret),
                mkt_vol_20=VALUES(mkt_vol_20),
                vol_threshold=VALUES(vol_threshold),
                high_vol_dummy=VALUES(high_vol_dummy),
                mkt_regime=VALUES(mkt_regime),
                cli=VALUES(cli),
                cli_lag1=VALUES(cli_lag1),
                cli_lag3=VALUES(cli_lag3),
                cli_lag6=VALUES(cli_lag6);
        """
        
        data = [tuple(row) for row in df.values]
        cur.executemany(sql, data)
        conn.commit()
        print(f"✅ COMMON_TB 업데이트 완료: {len(df)}건")
    except Exception as e:
        print(f"❌ DB 적재 오류: {e}")
        conn.rollback()
    finally:
        conn.close()

def run_common_indicator_calculator():
    print("🚀 공통 지표 계산 및 업데이트 중...")
    
    try:
        df_kospi = fetch_kospi200_naver(FETCH_START_DATE)
        
        if df_kospi.empty:
            raise ValueError("데이터가 비어 있습니다.")

        print(f"✅ 수집 성공: 최종 날짜 {df_kospi['trade_date'].max().date()}")

    except Exception as e:
        print(f"❌ KOSPI 200 수집 최종 실패: {e}")
        return
    
    client = EcosClient()
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = datetime.now().strftime("%Y%m")
    cli_raw = client.fetch_cli_data(ecos_start, ecos_end)
    
    final_df = calculate_common_indicators(df_kospi, cli_raw)
    send_to_common_db(final_df)

if __name__ == "__main__":
    run_common_indicator_calculator()