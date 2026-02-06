import pandas as pd

# ===============================
# 1) CSV 로드
# ===============================
fred = pd.read_csv("fred.csv")
ecos = pd.read_csv("ecos.csv")
jpy3 = pd.read_csv("jpy3.csv")
jpy10 = pd.read_csv("jpy10.csv")
pmi = pd.read_csv("pmi.csv")

# ===============================
# 2) 날짜 컬럼 통일
# ===============================
for d in (fred, ecos, jpy3, jpy10, pmi):
    d["date"] = pd.to_datetime(d["date"])

# ===============================
# 3) 날짜 기준 outer merge
# ===============================
df = (
    fred.merge(ecos, on="date", how="outer")
        .merge(jpy3, on="date", how="outer")
        .merge(jpy10, on="date", how="outer")
        .merge(pmi, on="date", how="outer")
        .sort_values("date")
        .reset_index(drop=True)
)

# ===============================
# 4) 컬럼 성격별 전처리
# ===============================

# (1) 월별/분기별 상태 변수 -> ffill
monthly_cols = [
    # 미국
    "us_cpi", "us_core_cpi", "us_core_pce", "us_unrate",
    # 한국/글로벌
    "cpi", "unemployment_rate", "ccsi",
    "export_total", "export_yoy",
    "import_total", "import_yoy",
    "gdp_level", "gdp_qoq",
    "wti", "brent",
    "pmi",
]
monthly_cols = [c for c in monthly_cols if c in df.columns]
df[monthly_cols] = df[monthly_cols].ffill()

# (2) 금융시장 변수(평일/휴일 결측) -> ffill 후 첫구간 bfill
market_cols = [
    "us_policy_rate", "us_ust_3y", "us_ust_10y",
    "ktb3y", "ktb10y", "usdkrw",
    "jpy3", "jpy10"
]
market_cols = [c for c in market_cols if c in df.columns]
df[market_cols] = df[market_cols].ffill().bfill()

if "base_rate" in df.columns:
    df["base_rate"] = df["base_rate"].ffill().bfill()

if "us_init_claims" in df.columns:
    df["us_init_claims"] = df["us_init_claims"].ffill().bfill()

# ===============================
# 5) 분석 시작 시점 컷
# ===============================
df = df[df["date"] >= "2023-01-01"].reset_index(drop=True)

# ===============================
# 6) 한·미 금리차 파생변수 생성 (미국 - 한국)
# ===============================
# 단기(정책) 금리차
if {"us_policy_rate", "base_rate"}.issubset(df.columns):
    df["rate_diff_policy"] = df["us_policy_rate"] - df["base_rate"]

# 중기(3년) 금리차
if {"us_ust_3y", "ktb3y"}.issubset(df.columns):
    df["rate_diff_3y"] = df["us_ust_3y"] - df["ktb3y"]

# 장기(10년) 금리차
if {"us_ust_10y", "ktb10y"}.issubset(df.columns):
    df["rate_diff_10y"] = df["us_ust_10y"] - df["ktb10y"]


# ===============================
# 7) 저장
# ===============================
df.to_csv("macroeconomics.csv", index=False)
print("✅ macroeconomics.csv 저장 완료")
