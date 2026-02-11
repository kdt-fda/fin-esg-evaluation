import os
import requests
import pandas as pd
import FinanceDataReader as fdr
from pandas.tseries.offsets import DateOffset
from dotenv import load_dotenv

# ============================================================
# 0. Configuration
# ============================================================
load_dotenv()
USER_START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
# 지표 계산(MA200, Vol Quantile)을 위해 수집 시작일을 2021년으로 확장
FETCH_START_DATE = '2021-01-01'
LAG_MONTHS = (1, 3, 6)

# ============================================================
# 1. ECOS Client (안정화 버전)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ECOS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ECOS_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        self.session = requests.Session()

    def _request(self, service, *args):
        path = "/".join(map(str, args))
        url = f"{self.BASE_URL}/{service}/{self.api_key}/json/kr/{path}"
        try:
            resp = self.session.get(url, timeout=30)
            return resp.json()
        except Exception as e:
            print(f"📡 API 요청 중 네트워크 오류: {e}")
            return {}

    def fetch_cli_data(self, start, end):
        """선행지수 순환변동치(901Y067 - I16E) 직접 수집"""
        # 통계표: 901Y067 (경기종합지수), 아이템: I16E (선행지수 순환변동치)
        # 안정성을 위해 검색 로직 대신 검증된 코드를 직접 사용합니다.
        path = [1, 1000, "901Y067", "M", start, end, "I16E"]
        data = self._request("StatisticSearch", *path)
        rows = data.get("StatisticSearch", {}).get("row", [])
        
        if not rows:
            print("⚠️ ECOS에서 데이터를 가져오지 못했습니다. 컬럼 없이 빈 DF를 반환합니다.")
            return pd.DataFrame(columns=["Date", "cli"])

        df = pd.DataFrame(rows)
        # Date 컬럼 강제 생성 및 형식 통일
        df["Date"] = pd.to_datetime(df["TIME"], format="%Y%m", errors='coerce').dt.normalize()
        df["cli"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        return df[["Date", "cli"]].dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

# ============================================================
# 2. Data Processing Helpers
# ============================================================
def calculate_regime_indicators(df_kospi: pd.DataFrame) -> pd.DataFrame:
    df = df_kospi.copy().sort_values("Date")
    
    # 1) 추세 기반 (Bull Dummy)
    df['MA200'] = df['Close_kospi200'].rolling(window=200, min_periods=100).mean()
    df['bull_dummy'] = (df['Close_kospi200'] > df['MA200']).astype(int)

    # 2) 변동성 기반 (High Vol Dummy)
    df['mkt_ret'] = df['Close_kospi200'].pct_change()
    df['mkt_vol_20'] = df['mkt_ret'].rolling(window=20, min_periods=20).std()
    
    # 252일 Rolling Quantile
    df['vol_threshold'] = df['mkt_vol_20'].rolling(window=252, min_periods=100).quantile(0.8)
    df['high_vol_dummy'] = (df['mkt_vol_20'] > df['vol_threshold']).astype(int)

    # 3) Regime 통합
    df['mkt_regime'] = df['bull_dummy'] * 2 + df['high_vol_dummy']
    
    return df

def add_lags(df: pd.DataFrame, lags=(1, 3, 6)) -> pd.DataFrame:
    # 'Date' 컬럼이 있는지 확인 (KeyError 방어)
    if df.empty or "Date" not in df.columns:
        print("⚠️ [add_lags] 유효한 데이터가 없어 빈 DF를 반환합니다.")
        return df
        
    df = df.sort_values("Date").reset_index(drop=True)
    for k in lags:
        df[f"cli_lag{k}"] = df["cli"].shift(k)
    return df

# ============================================================
# 3. Main Execution
# ============================================================
if __name__ == "__main__":
    # --- Part A: KOSPI 200 지수 및 레짐 계산 ---
    print("🚀 KOSPI 200 데이터 수집 및 지표 계산 중...")
    df_kospi = fdr.DataReader('KS200', start=FETCH_START_DATE, end=END_DATE)
    df_kospi = df_kospi[['Close']].reset_index()
    df_kospi = df_kospi.rename(columns={'Close': 'Close_kospi200'})
    df_kospi['Date'] = pd.to_datetime(df_kospi['Date']).dt.normalize()
    
    df_kospi = calculate_regime_indicators(df_kospi)

    # --- Part B: ECOS CLI 데이터 수집 ---
    print("🚀 ECOS CLI 데이터 수집 중...")
    client = EcosClient()
    
    # Lag 계산을 위해 수집 기간 확장
    ecos_start = pd.to_datetime(FETCH_START_DATE).strftime("%Y%m")
    ecos_end = pd.to_datetime(END_DATE).strftime("%Y%m")

    cli_raw = client.fetch_cli_data(ecos_start, ecos_end)
    
    # 데이터 유무 확인 후 시차 변수 생성
    cli_final = add_lags(cli_raw, lags=LAG_MONTHS)
    
    # --- Part C: 데이터 병합 (Merge Asof) ---
    print("🚀 데이터 병합 및 결측치 보정 중...")
    
    # Dtype 강제 고정 (MergeError 방어)
    df_kospi['Date'] = df_kospi['Date'].astype('datetime64[ns]')
    
    if not cli_final.empty:
        cli_final['Date'] = cli_final['Date'].astype('datetime64[ns]')
        
        merged = pd.merge_asof(
            df_kospi.sort_values("Date"),
            cli_final.sort_values("Date"),
            on="Date",
            direction="backward"
        )
        # 월간 데이터를 일간으로 채우기
        cli_cols = ['cli'] + [f"cli_lag{k}" for k in LAG_MONTHS]
        merged[cli_cols] = merged[cli_cols].ffill()
    else:
        print("⚠️ CLI 데이터가 없어 주가 데이터만 유지합니다.")
        merged = df_kospi

    # --- Part D: 최종 저장 ---
    final_df = merged[merged["Date"] >= USER_START_DATE].copy()
    
    print("-" * 30)
    print(f"📊 최종 데이터 시작일: {final_df['Date'].min() if not final_df.empty else 'N/A'}")
    print(f"📊 컬럼별 NaN 개수:\n{final_df.isnull().sum()}")
    
    final_df.to_csv("common_processed.csv", index=False, encoding="utf-8-sig")
    print(f"\n✅ 공통 지표 전처리 완료: common_processed.csv (총 {len(final_df)}행)")
    print(final_df.head(10))