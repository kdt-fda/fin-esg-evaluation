import os
import requests
import pandas as pd

# ============================================================
# 0) 기본 설정
# ============================================================
API_KEY = os.getenv("ECOS_API_KEY")
if not API_KEY:
    raise RuntimeError("ECOS_API_KEY 환경변수가 없습니다.")

BASE_URL = "https://ecos.bok.or.kr/api"

# 수집 기간
START_D = "20230101"
END_D   = "20251231"

START_M = "202301"
END_M   = "202512"

#수출/수입 YoY 계산용: 12개월 이전 값 필요하므로 2022년부터 확보
TRADE_START_M = "202201"

START_Q = "2022Q4"   # QoQ 계산하려면 직전 분기 필요
END_Q   = "2025Q4"

# 최종 저장 시 분석 구간
FINAL_CUT_START = "2023-01-01"

# ============================================================
# 1) ECOS 유틸
# ============================================================
def _get_json(url, timeout=30):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

def ecos_table_name(stat_code, page_size=5000):
    url = f"{BASE_URL}/StatisticTableList/{API_KEY}/json/kr/1/{page_size}/{stat_code}"
    j = _get_json(url)
    if "RESULT" in j and j["RESULT"].get("CODE") != "INFO-000":
        return ""
    rows = j.get("StatisticTableList", {}).get("row", [])
    if not rows:
        return ""
    return rows[0].get("STAT_NAME", "") or rows[0].get("STAT_NAME_KOR", "") or ""

def ecos_itemlist(stat_code, page_size=5000):
    url = f"{BASE_URL}/StatisticItemList/{API_KEY}/json/kr/1/{page_size}/{stat_code}"
    j = _get_json(url)
    if "RESULT" in j and j["RESULT"].get("CODE") != "INFO-000":
        raise RuntimeError(f"StatisticItemList 오류: {j['RESULT']}")
    rows = j.get("StatisticItemList", {}).get("row", [])
    return pd.DataFrame(rows)

def detect_item_code_col(df):
    for col in ["ITEM_CODE1", "ITEM_CODE", "ITEM_CODE2", "ITEM_CODE3"]:
        if col in df.columns:
            return col
    return None

def ecos_fetch(stat, item, cycle, start, end, colname):
    url_base = f"{BASE_URL}/StatisticSearch/{API_KEY}/json/kr"
    page_size, start_no = 1000, 1
    out, total_cnt = [], None

    item_path = str(item)

    while True:
        url = f"{url_base}/{start_no}/{start_no+page_size-1}/{stat}/{cycle}/{start}/{end}/{item_path}"
        j = _get_json(url)

        if "RESULT" in j and j["RESULT"].get("CODE") == "INFO-200":
            return None, f"INFO-200 | stat={stat} item={item_path} cycle={cycle} start={start} end={end}"

        if "StatisticSearch" not in j:
            msg = f"unexpected response keys={list(j.keys())}"
            if "RESULT" in j:
                msg += f" | RESULT={j['RESULT']}"
            return None, msg

        meta = j["StatisticSearch"]
        rows = meta.get("row", [])
        if total_cnt is None:
            total_cnt = int(meta.get("list_total_count", 0))

        if not rows:
            break

        out.extend(rows)
        if len(out) >= total_cnt:
            break

        start_no += page_size

    df = pd.DataFrame(out)[["TIME", "DATA_VALUE"]].copy()

    # 날짜 파싱
    if cycle == "Q":
        df["date"] = pd.PeriodIndex(df["TIME"].astype(str), freq="Q").to_timestamp()
    elif cycle == "M":
        df["date"] = pd.to_datetime(df["TIME"], format="%Y%m")
    elif cycle == "D":
        df["date"] = pd.to_datetime(df["TIME"], format="%Y%m%d")
    else:
        df["date"] = pd.to_datetime(df["TIME"], errors="coerce")

    df[colname] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    df = df[["date", colname]].sort_values("date").reset_index(drop=True)
    return df, "resolved"

def ecos_fetch_raw(stat, item, cycle, start, end, value_col):
    url_base = f"{BASE_URL}/StatisticSearch/{API_KEY}/json/kr"
    page_size, start_no = 1000, 1
    out, total_cnt = [], None

    item_path = str(item)

    while True:
        url = f"{url_base}/{start_no}/{start_no+page_size-1}/{stat}/{cycle}/{start}/{end}/{item_path}"
        j = _get_json(url)

        if "RESULT" in j and j["RESULT"].get("CODE") == "INFO-200":
            return None, f"INFO-200 | stat={stat} item={item_path} cycle={cycle} start={start} end={end}"

        if "StatisticSearch" not in j:
            msg = f"unexpected response keys={list(j.keys())}"
            if "RESULT" in j:
                msg += f" | RESULT={j['RESULT']}"
            return None, msg

        meta = j["StatisticSearch"]
        rows = meta.get("row", [])
        if total_cnt is None:
            total_cnt = int(meta.get("list_total_count", 0))

        if not rows:
            break

        out.extend(rows)
        if len(out) >= total_cnt:
            break

        start_no += page_size

    df = pd.DataFrame(out)

    # 날짜 파싱
    if cycle == "M":
        df["date"] = pd.to_datetime(df["TIME"], format="%Y%m")
    elif cycle == "D":
        df["date"] = pd.to_datetime(df["TIME"], format="%Y%m%d")
    elif cycle == "Q":
        df["date"] = pd.PeriodIndex(df["TIME"].astype(str), freq="Q").to_timestamp()
    else:
        df["date"] = pd.to_datetime(df["TIME"], errors="coerce")

    df[value_col] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")

    keep_cols = ["date", value_col]
    for c in ["ITEM_CODE1","ITEM_CODE2","ITEM_CODE3","ITEM_NAME1","ITEM_NAME2","ITEM_NAME3","UNIT_NAME"]:
        if c in df.columns:
            keep_cols.append(c)

    df = df[keep_cols].sort_values("date").reset_index(drop=True)
    return df, "resolved"

def get_item_meta(stat_code, item_code):
    try:
        items = ecos_itemlist(stat_code)
        code_col = detect_item_code_col(items)
        if items.empty or not code_col:
            return "", ""
        hit = items[items[code_col].astype(str) == str(item_code)]
        if hit.empty:
            return "", ""
        item_name = hit.iloc[0].get("ITEM_NAME", "") or ""
        unit_name = hit.iloc[0].get("UNIT_NAME", "") or ""
        return item_name, unit_name
    except Exception:
        return "", ""

def ensure_unique_date(df, value_cols):
    if df is None or df.empty:
        return df
    dup = df["date"].duplicated().sum()
    if dup > 0:
        df = df.groupby("date", as_index=False)[value_cols].mean()
    return df

def make_yoy(level_df, value_col, out_col):
    x = level_df.copy()
    x[out_col] = x[value_col].pct_change(12) * 100
    return x[["date", out_col]]

# ============================================================
# 2) 수집 대상 정의
# ============================================================
SERIES_DAILY = [
    dict(name="ktb3y",     stat="817Y002", item="010200000", cycle="D", start=START_D, end=END_D, note="국고채(3년)"),
    dict(name="ktb10y",    stat="817Y002", item="010210000", cycle="D", start=START_D, end=END_D, note="국고채(10년)"),
    dict(name="usdkrw",    stat="731Y003", item="0000003",   cycle="D", start=START_D, end=END_D, note="원/달러(15:30)"),
    dict(name="base_rate", stat="722Y001", item="0101000",   cycle="D", start=START_D, end=END_D, note="한국은행 기준금리"),
]

SERIES_MONTHLY = [
    dict(name="wti",      stat="902Y003", item="010101", cycle="M", start=START_M, end=END_M, note="WTI"),
    dict(name="brent",    stat="902Y003", item="010103", cycle="M", start=START_M, end=END_M, note="Brent"),
    dict(name="cpi",      stat="901Y009", item="0",      cycle="M", start=START_M, end=END_M, note="CPI"),
    dict(name="unemployment_rate", stat="901Y027", item="I61BC", cycle="M", start=START_M, end=END_M, note="실업률"),
    dict(name="ccsi",     stat="511Y002", item="FME",    cycle="M", start=START_M, end=END_M, note="CCSI"),
]

GDP_SPEC = dict(
    gdp_level=dict(name="gdp_level", stat="200Y108", item="10601", cycle="Q", start=START_Q, end=END_Q, note="실질GDP(계절조정)")
)

# ============================================================
# 3) 실행: 수집 + 파생 + 병합 + 로그
# ============================================================
log_rows = []
dfs = {}

def add_log(name, status, stat, item, cycle, start, end, rows, message, note):
    stat_name = ecos_table_name(stat)
    item_name, unit = get_item_meta(stat, item)
    log_rows.append({
        "name": name,
        "status": status,
        "stat": stat,
        "stat_name": stat_name,
        "item": item,
        "item_name": item_name,
        "unit": unit,
        "cycle": cycle,
        "start": start,
        "end": end,
        "rows": rows,
        "message": message,
        "note": note
    })

# 3-1) 일별 수집
for s in SERIES_DAILY:
    df, msg = ecos_fetch(s["stat"], s["item"], s["cycle"], s["start"], s["end"], s["name"])
    if df is None or df.empty:
        add_log(s["name"], "FAIL", s["stat"], s["item"], s["cycle"], s["start"], s["end"], 0, msg, s["note"])
        print(f"{s['name']}: FAIL ({msg})")
        continue
    df = ensure_unique_date(df, [s["name"]])
    dfs[s["name"]] = df
    add_log(s["name"], "OK", s["stat"], s["item"], s["cycle"], s["start"], s["end"], len(df), "resolved", s["note"])
    print(f"{s['name']}: OK rows={len(df):,}")

# 3-2) 월별 수집
for s in SERIES_MONTHLY:
    df, msg = ecos_fetch(s["stat"], s["item"], s["cycle"], s["start"], s["end"], s["name"])
    if df is None or df.empty:
        add_log(s["name"], "FAIL", s["stat"], s["item"], s["cycle"], s["start"], s["end"], 0, msg, s["note"])
        print(f"{s['name']}: FAIL ({msg})")
        continue
    df = ensure_unique_date(df, [s["name"]])
    dfs[s["name"]] = df
    add_log(s["name"], "OK", s["stat"], s["item"], s["cycle"], s["start"], s["end"], len(df), "resolved", s["note"])
    print(f"{s['name']}: OK rows={len(df):,}")

# ============================================================
# 3-3) 수출/수입: YoY 계산 위해 2022-01부터 수집
# ============================================================

# export: 901Y119 / T002 (수출금액)
export_raw, msg = ecos_fetch_raw("901Y119", "T002", "M", TRADE_START_M, END_M, "export_level")
if export_raw is None or export_raw.empty:
    add_log("export_total", "FAIL", "901Y119", "T002", "M", TRADE_START_M, END_M, 0, msg, "총수출(대륙 합산)")
    print(f"export_total: FAIL ({msg})")
else:
    export_total = export_raw.groupby("date", as_index=False)["export_level"].sum().sort_values("date")
    export_total = export_total.rename(columns={"export_level": "export_total"})
    dfs["export_total"] = export_total
    add_log("export_total", "OK", "901Y119", "T002", "M", TRADE_START_M, END_M, len(export_total), "computed_sum_by_continent", "총수출(대륙 합산)")
    print(f"export_total: OK rows={len(export_total):,} | computed(sum)")

    dfs["export_yoy"] = make_yoy(export_total, "export_total", "export_yoy")
    add_log("export_yoy", "OK", "901Y119", "T002", "M", TRADE_START_M, END_M, len(dfs["export_yoy"]), "computed_from_export_total", "총수출 YoY(%): pct_change(12)*100")
    print(f"export_yoy: OK rows={len(dfs['export_yoy']):,} | computed")

# import: 901Y119 / T004 (수입금액)
import_raw, msg = ecos_fetch_raw("901Y119", "T004", "M", TRADE_START_M, END_M, "import_level")
if import_raw is None or import_raw.empty:
    add_log("import_total", "FAIL", "901Y119", "T004", "M", TRADE_START_M, END_M, 0, msg, "총수입(대륙 합산)")
    print(f"import_total: FAIL ({msg})")
else:
    import_total = import_raw.groupby("date", as_index=False)["import_level"].sum().sort_values("date")
    import_total = import_total.rename(columns={"import_level": "import_total"})
    dfs["import_total"] = import_total
    add_log("import_total", "OK", "901Y119", "T004", "M", TRADE_START_M, END_M, len(import_total), "computed_sum_by_continent", "총수입(대륙 합산)")
    print(f"import_total: OK rows={len(import_total):,} | computed(sum)")

    dfs["import_yoy"] = make_yoy(import_total, "import_total", "import_yoy")
    add_log("import_yoy", "OK", "901Y119", "T004", "M", TRADE_START_M, END_M, len(dfs["import_yoy"]), "computed_from_import_total", "총수입 YoY(%): pct_change(12)*100")
    print(f"import_yoy: OK rows={len(dfs['import_yoy']):,} | computed")

# 3-4) GDP level 수집 + QoQ 계산
gdp_level_df, gdp_msg = ecos_fetch(
    stat=GDP_SPEC["gdp_level"]["stat"],
    item=GDP_SPEC["gdp_level"]["item"],
    cycle=GDP_SPEC["gdp_level"]["cycle"],
    start=GDP_SPEC["gdp_level"]["start"],
    end=GDP_SPEC["gdp_level"]["end"],
    colname="gdp_level"
)

if gdp_level_df is None or gdp_level_df.empty:
    add_log("gdp_level", "FAIL", GDP_SPEC["gdp_level"]["stat"], GDP_SPEC["gdp_level"]["item"],
            "Q", START_Q, END_Q, 0, gdp_msg, GDP_SPEC["gdp_level"]["note"])
    print(f"⚠️ gdp_level: FAIL ({gdp_msg})")
else:
    gdp_level_df = ensure_unique_date(gdp_level_df, ["gdp_level"])
    dfs["gdp_level"] = gdp_level_df
    add_log("gdp_level", "OK", GDP_SPEC["gdp_level"]["stat"], GDP_SPEC["gdp_level"]["item"],
            "Q", START_Q, END_Q, len(gdp_level_df), "resolved", GDP_SPEC["gdp_level"]["note"])
    print(f"gdp_level: OK rows={len(gdp_level_df):,}")

    tmp = gdp_level_df.copy()
    tmp["gdp_qoq"] = (tmp["gdp_level"] / tmp["gdp_level"].shift(1) - 1) * 100
    tmp = tmp.dropna(subset=["gdp_qoq"])[["date", "gdp_qoq"]].reset_index(drop=True)
    dfs["gdp_qoq"] = tmp

    add_log("gdp_qoq", "OK", GDP_SPEC["gdp_level"]["stat"], GDP_SPEC["gdp_level"]["item"],
            "Q", START_Q, END_Q, len(tmp), "computed_from_level", "QoQ: (t/t-1 -1)*100")
    print(f"gdp_qoq: OK rows={len(tmp):,} | computed")

# ============================================================
# 4) 병합: date 기준 outer join
# ============================================================
merge_order = [
    "ktb3y", "ktb10y", "usdkrw", "base_rate",
    "wti", "brent", "cpi", "unemployment_rate", "ccsi",
    "export_total", "export_yoy",
    "import_total", "import_yoy",
    "gdp_level", "gdp_qoq"
]

merged = None
for k in merge_order:
    if k not in dfs:
        continue
    if merged is None:
        merged = dfs[k].copy()
    else:
        merged = pd.merge(merged, dfs[k], on="date", how="outer")

if merged is None:
    raise RuntimeError("수집된 데이터가 없습니다. 로그(ecos_log.csv)를 확인하세요.")

merged = merged.sort_values("date").reset_index(drop=True)

# 최종 분석 구간으로 컷 
merged = merged[merged["date"] >= pd.to_datetime(FINAL_CUT_START)].reset_index(drop=True)

# ============================================================
# 5) 저장
# ============================================================
merged.to_csv("ecos.csv", index=False, encoding="utf-8-sig")
print("저장 완료: ecos.csv")

log_df = pd.DataFrame(log_rows)
log_df.to_csv("ecos_log.csv", index=False, encoding="utf-8-sig")
print("로그 저장: ecos_log.csv")

