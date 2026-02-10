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
START_DATE = '2023-01-01'
END_DATE = '2025-12-31'
LAG_MONTHS = (1, 3, 6)

# ============================================================
# 1. ECOS Client (데이터 수집 클래스)
# ============================================================
class EcosClient:
    BASE_URL = "https://ecos.bok.or.kr/api"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ECOS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ECOS_API_KEY 환경변수가 설정되지 않았습니다.")
        self.session = requests.Session()

    def _request(self, service, *args):
        path = "/".join(map(str, args))
        url = f"{self.BASE_URL}/{service}/{self.api_key}/json/kr/{path}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        res_info = data.get("RESULT") or data.get(service, {}).get("RESULT")
        if res_info and res_info.get("CODE") not in ["INFO-000", "INFO-200"]:
            raise RuntimeError(f"API 에러: {res_info.get('MESSAGE')} ({res_info.get('CODE')})")
        return data

    def get_target_info(self):
        """최적의 통계표 및 아이템 코드 탐색 통합"""
        # 통계표 탐색
        rows = self._request("StatisticTableList", 1, 5000).get("StatisticTableList", {}).get("row", [])
        df_table = pd.DataFrame(rows)
        patt = r"(?:경기\s*종합지수|선행\s*종합지수|순환변동치|CLI)"
        cand = df_table[df_table["STAT_NAME"].str.contains(patt, regex=True, na=False)].copy()
        
        if cand.empty:
            return "901Y067", "M", ["I16D"], "선행종합지수(2020=100)"

        cand["score"] = (cand["CYCLE"].eq("M") * 5 + cand["STAT_NAME"].str.contains("경기종합지수") * 4)
        top_table = cand.sort_values("score", ascending=False).iloc[0]
        stat_code, cycle = top_table["STAT_CODE"], top_table["CYCLE"]

        # 아이템 탐색
        item_rows = self._request("StatisticItemList", 1, 5000, stat_code).get("StatisticItemList", {}).get("row", [])
        df_item = pd.DataFrame(item_rows)
        item_patt = r"(?:선행|종합|순환변동치|CLI)"
        df_item["score"] = df_item["ITEM_NAME"].str.contains(item_patt, regex=True).astype(int)
        top_item = df_item.sort_values("score", ascending=False).iloc[0]
        
        item_code_col = "ITEM_CODE1" if "ITEM_CODE1" in df_item.columns else "ITEM_CODE"
        return stat_code, cycle, [top_item[item_code_col]], top_item["ITEM_NAME"]

    def fetch_cli_data(self, stat_code, cycle, start, end, item_codes):
        path = [1, 1000, stat_code, cycle, start, end] + (item_codes or [])
        rows = self._request("StatisticSearch", *path).get("StatisticSearch", {}).get("row", [])
        
        if not rows: return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["TIME"], format="%Y%m" if cycle == "M" else None, errors="coerce")
        df["cli"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        return df[["Date", "cli"]].dropna().sort_values("Date").reset_index(drop=True)

# ============================================================
# 2. Data Processing Helpers
# ============================================================
def calculate_regime_indicators(df_kospi: pd.DataFrame) -> pd.DataFrame:
    """KOSPI200 기반 레짐 더미 생성 파이프라인"""
    df = df_kospi.copy()
    
    # 1) 추세 기반 (Bull Dummy)
    df['MA200'] = df['Close_kospi200'].rolling(window=200, min_periods=200).mean()
    df['bull_dummy'] = (df['Close_kospi200'] > df['MA200']).astype(int)

    # 2) 변동성 기반 (High Vol Dummy)
    df['mkt_ret'] = df['Close_kospi200'].pct_change()
    df['mkt_vol_20'] = df['mkt_ret'].rolling(window=20, min_periods=20).std()
    
    # Rolling Quantile (Lookback: 252 days)
    df['vol_threshold'] = df['mkt_vol_20'].rolling(window=252, min_periods=252).quantile(0.8).shift(1)
    df['high_vol_dummy'] = (df['mkt_vol_20'] > df['vol_threshold']).astype(int)

    # 3) Regime 통합 (0~3)
    df['mkt_regime'] = df['bull_dummy'] * 2 + df['high_vol_dummy']
    
    return df.drop(columns=['mkt_ret']) # 학습에 불필요한 중간값 제거 선택

def add_lags(df: pd.DataFrame, lags=(1, 3, 6)) -> pd.DataFrame:
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
    df_kospi = fdr.DataReader('KS200', start=START_DATE, end=END_DATE)
    df_kospi = df_kospi[['Close']].reset_index()
    df_kospi = df_kospi.rename(columns={'Close': 'Close_kospi200'})
    df_kospi = calculate_regime_indicators(df_kospi)

    # --- Part B: ECOS CLI 데이터 수집 ---
    print("🚀 ECOS CLI 데이터 수집 중...")
    client = EcosClient()
    stat_code, cycle, item_codes, item_name = client.get_target_info()
    
    # 기간 확장 계산 (Lag 고려)
    max_lag = max(LAG_MONTHS)
    start_dt = pd.to_datetime(START_DATE)
    ecos_start = (start_dt - DateOffset(months=max_lag)).strftime("%Y%m")
    ecos_end = pd.to_datetime(END_DATE).strftime("%Y%m")

    cli_raw = client.fetch_cli_data(stat_code, cycle, ecos_start, ecos_end, item_codes)
    cli_final = add_lags(cli_raw, lags=LAG_MONTHS)
    
    # 사용자 요청 기간 필터링
    cli_final = cli_final[
        (cli_final["Date"] >= START_DATE) & (cli_final["Date"] <= END_DATE)
    ].reset_index(drop=True)

    # --- Part C: 데이터 병합 (Merge Asof) ---
    print("🚀 데이터 병합 중...")
    # 시계열 병합을 위해 정렬 보장
    df_kospi = df_kospi.sort_values("Date")
    cli_final = cli_final.sort_values("Date")

    merged = pd.merge_asof(
        df_kospi,
        cli_final,
        on="Date",
        direction="backward"
    )

    # --- Part D: 결과 출력 및 저장 ---
    print("-" * 30)
    print(merged.tail(10))
    print(f"\n최종 데이터 형태: {merged.shape}")
    
    merged.to_csv("common_processed.csv", index=False, encoding="utf-8-sig")