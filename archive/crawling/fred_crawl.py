import os
import requests
import pandas as pd

START = "2023-01-01"
END   = "2025-12-31"

API_KEY = os.getenv("FRED_API_KEY")
if not API_KEY:
    raise RuntimeError("FRED_API_KEY 환경변수가 없습니다.")

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

series = {
    "us_cpi": "CPIAUCSL",
    "us_core_cpi": "CPILFESL",
    "us_core_pce": "PCEPILFE",
    "us_unrate": "UNRATE",
    "us_init_claims": "ICSA",
    "us_policy_rate": "EFFR",
    "us_ust_3y": "DGS3",
    "us_ust_10y": "DGS10"
}

dfs = []

for col, sid in series.items():
    params = {
        "series_id": sid,
        "api_key": API_KEY,
        "file_type": "json",
        "observation_start": START,
        "observation_end": END,
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        obs = j.get("observations", [])
        tmp = pd.DataFrame(obs)[["date", "value"]].copy()
        tmp["date"] = pd.to_datetime(tmp["date"])
        tmp[col] = pd.to_numeric(tmp["value"], errors="coerce")
        tmp = tmp[["date", col]].set_index("date")
        dfs.append(tmp)
        print(f"✅ OK: {sid} -> {col} | rows={len(tmp):,}")
    except Exception as e:
        failed.append((col, sid, str(e)[:200]))
        print(f"⚠️ SKIP: {sid} -> {col} | {str(e)[:120]}")

df = pd.concat(dfs, axis=1).reset_index()
df.to_csv("fred.csv", index=False, encoding="utf-8-sig")

print("\n✅ 저장 완료: fred.csv")
print(df.head())
