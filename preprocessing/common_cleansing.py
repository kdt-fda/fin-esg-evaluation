import FinanceDataReader as fdr
import os
import requests
import pandas as pd
from pandas.tseries.offsets import DateOffset
from dotenv import load_dotenv
load_dotenv()

start_date = '2023-01-01'
end_date = '2025-12-31'

# 1. 코스피200 지수
kospi200 = fdr.DataReader('KS200', start=start_date, end=end_date)
kospi200 = kospi200['Close']
kospi200 = kospi200.reset_index()
# kospi200.to_csv('KOSPI200.csv', index=False)

# 2. 경기선행지수 lag
# ============================================================
# ECOS Client
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

        # 결과 코드 확인
        res_info = data.get("RESULT") or data.get(service, {}).get("RESULT")
        if res_info and res_info.get("CODE") not in ["INFO-000", "INFO-200"]:
            raise RuntimeError(f"API 에러: {res_info.get('MESSAGE')} ({res_info.get('CODE')})")
        return data

    def get_best_stat_code(self):
        """경기종합지수 관련 최적의 통계표 탐색"""
        rows = self._request("StatisticTableList", 1, 5000).get("StatisticTableList", {}).get("row", [])
        df = pd.DataFrame(rows)

        # 경기/선행/순환변동치 키워드 탐색 (Warning 방지용 (?:) 사용)
        patt = r"(?:경기\s*종합지수|선행\s*종합지수|순환변동치|CLI)"
        cand = df[df["STAT_NAME"].str.contains(patt, regex=True, na=False)].copy()

        if cand.empty:
            return "901Y067", "M"  # 폴백값

        cand["score"] = (cand["CYCLE"].eq("M") * 5 + cand["STAT_NAME"].str.contains("경기종합지수") * 4)
        top = cand.sort_values("score", ascending=False).iloc[0]
        return top["STAT_CODE"], top["CYCLE"]

    def get_best_item_code(self, stat_code):
        """통계표 내에서 '선행지수' 아이템 탐색"""
        rows = self._request("StatisticItemList", 1, 5000, stat_code).get("StatisticItemList", {}).get("row", [])
        df = pd.DataFrame(rows)
        if df.empty:
            return None, None

        item_patt = r"(?:선행|종합|순환변동치|CLI)"
        df["score"] = df["ITEM_NAME"].str.contains(item_patt, regex=True).astype(int)
        top = df.sort_values("score", ascending=False).iloc[0]

        code_col = "ITEM_CODE1" if "ITEM_CODE1" in df.columns else "ITEM_CODE"
        return [top[code_col]], top["ITEM_NAME"]

    def fetch_cli_data(self, stat_code, cycle, start, end, item_codes):
        """데이터 수집 및 'cli' 컬럼으로 정리"""
        path = [1, 1000, stat_code, cycle, start, end] + (item_codes or [])
        rows = self._request("StatisticSearch", *path).get("StatisticSearch", {}).get("row", [])

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # TIME 형식: 월(M)=YYYYMM
        if cycle == "M":
            df["date"] = pd.to_datetime(df["TIME"], format="%Y%m")
        else:
            # 분기/연 등은 상황에 따라 format이 달라질 수 있어, 일단 pandas에 위임
            df["date"] = pd.to_datetime(df["TIME"], errors="coerce")

        df["cli"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")

        return df[["date", "cli"]].dropna().sort_values("date").reset_index(drop=True)


# ============================================================
# Helpers
# ============================================================
def ym_for_ecos(d: pd.Timestamp) -> str:
    return d.strftime("%Y%m")


def expand_start_for_lag(start_date: str, max_lag_months: int) -> str:
    """
    lag 계산을 위해 start를 max_lag만큼 과거로 확장(월단위).
    예) start_date=2023-01-01, max_lag=6 -> ECOS 요청 start=202207
    """
    start = pd.to_datetime(start_date)
    expanded = (start - DateOffset(months=max_lag_months)).replace(day=1)
    return ym_for_ecos(expanded)


def end_ym_for_ecos(end_date: str) -> str:
    """ECOS 월자료 요청용 end YYYYMM"""
    end = pd.to_datetime(end_date)
    return ym_for_ecos(end.replace(day=1))


def add_lags(df: pd.DataFrame, lags=(1, 3, 6)) -> pd.DataFrame:
    """cli에 대해 lag 컬럼 생성 (과거값: shift(+k))"""
    df = df.sort_values("date").reset_index(drop=True)
    for k in lags:
        df[f"cli_lag{k}"] = df["cli"].shift(k)
    return df


def filter_user_range(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """최종 산출 기간 필터 (inclusive)"""
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    return df[(df["date"] >= s) & (df["date"] <= e)].reset_index(drop=True)


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    client = EcosClient()

    # 필요한 lag (개월)
    lags = (1, 3, 6)
    max_lag = max(lags)

    # 1) 대상 선정
    stat_code, cycle = client.get_best_stat_code()
    item_codes, item_name = client.get_best_item_code(stat_code)

    if not item_codes:
        raise RuntimeError("통계표 내에서 CLI/선행 관련 ITEM을 찾지 못했습니다.")

    print(f"탐색 결과: stat_code={stat_code}, item={item_name}, cycle={cycle}")

    # 2) ECOS 요청기간 산출 (lag 계산 위해 start 확장)
    ecos_start_ym = expand_start_for_lag(start_date, max_lag_months=max_lag)
    ecos_end_ym = end_ym_for_ecos(end_date)

    # 3) 데이터 수집
    cli_raw = client.fetch_cli_data(stat_code, cycle, ecos_start_ym, ecos_end_ym, item_codes)

    if cli_raw.empty:
        print("수집된 데이터가 없습니다.")
        raise SystemExit(1)

    # 4) lag 컬럼 생성
    cli_with_lags = add_lags(cli_raw, lags=lags)

    # 5) 사용자 기간으로 필터링 (최종 결과)
    cli_final = filter_user_range(cli_with_lags, start_date, end_date)
    cli_final = cli_final.rename(columns={"date": "Date"})

    # 6) 저장
    # out_path = "CLI_with_lags.csv"
    # cli_final.to_csv(out_path, index=False, encoding="utf-8-sig")

    # print(f"저장 완료: {out_path} (총 {len(cli_final)}행)")
    # print(cli_final.head(10))

# 3. 레짐 더미
# 추세 기반
# 200일 이동평균
kospi200['MA200'] = kospi200['KOSPI200_Close'].rolling(window=200, min_periods=200).mean()

# Bull regime dummy (1 = 상승, 0 = 하락/조정)
kospi200['bull_dummy'] = (kospi200['KOSPI200_Close'] > kospi200['MA200']).astype(int)

# 변동성 기반
# 일간 수익률
kospi200['mkt_ret_1'] = kospi200['KOSPI200_Close'].pct_change()

# 20일 변동성
kospi200['mkt_vol_20'] = kospi200['mkt_ret_1'].rolling(window=20, min_periods=20).std()

# 과거만 사용한 rolling quantile (예: 최근 252거래일 = 약 1년 기준)
lookback = 252
q = 0.8

kospi200['vol_threshold_80th'] = (
    kospi200['mkt_vol_20']
    .rolling(window=252, min_periods=252)
    .quantile(0.8)
    .shift(1)
)

kospi200['high_vol_dummy'] = (
    kospi200['mkt_vol_20'] > kospi200['vol_threshold_80th']
).astype(int)

# 0 = 하락, 안정 / 1 = 하락, 불안 / 2 = 상승, 안정 / 3 = 상승, 과열
kospi200['mkt_regime'] = kospi200['bull_dummy'] * 2 + kospi200['high_vol_dummy']
# kospi200[['Date', 'bull_dummy', 'high_vol_dummy', 'mkt_regime']].to_csv('regime_dummy.csv', index=False)


# ============================================================
# ** 파생변수 합치기 (KOSPI200 + CLI lags + regime dummy) **
#   - kospi200: 일자료(Date)
#   - cli_final: 월자료(Date)
#   - 결합 방식: 월 CLI를 일자로 forward-fill (merge_asof)
# ============================================================

# 0) 컬럼 정리: kospi200도 Date로 통일
kospi200 = kospi200.rename(columns={"Date": "Date"})  # 이미 Date면 영향 없음
kospi200["Date"] = pd.to_datetime(kospi200["Date"])
cli_final["Date"] = pd.to_datetime(cli_final["Date"])

# 1) (권장) 월 CLI를 "그 달의 값이 언제부터 유효한가" 기준으로 일자에 붙이기
#    - 보통 월 CLI는 '해당 월 값'이 월말/익월 초에 발표되므로,
#      정보누수 방지하려면 발표일 기준이 필요하지만 여기서는 일단 단순히 "월 시작부터 유효"로 가정.
#    - 즉, 2023-01 CLI는 2023-01-01부터 적용되는 것으로 붙음.

# (선택) 월 시작 기준으로 명확히 정렬
cli_m = cli_final.sort_values("Date").copy()
kospi_d = kospi200.sort_values("Date").copy()

# 2) asof merge: 각 일자에 대해 "가장 최근 월(Date)"의 CLI를 붙임 (forward-fill 효과)
merged = pd.merge_asof(
    kospi_d,
    cli_m,
    on="Date",
    direction="backward",   # 해당 일자보다 같거나 이전의 가장 최근 CLI(월)
    allow_exact_matches=True
)

# 3) 결과 저장(원하면)
# merged.to_csv("derivative_common.csv", index=False, encoding="utf-8-sig")

# 4) 확인
print(merged.head(20))
print("rows:", len(merged))