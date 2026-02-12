import os
import re
import numpy as np
import pandas as pd
import OpenDartReader
import FinanceDataReader as fdr
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DART_API_KEY")

dart = OpenDartReader(api_key)



# 0) MAPPING
BS_ACCOUNT_MAP = {
    "assets": ["자산총계", "총자산"],
    "liabilities": ["부채총계", "총부채"],
    "equity": ["자본총계", "총자본"],
    "cash": ["현금및현금성자산", "현금및현금성자산합계","현금및현금성자산및현금성자산", "현금및예치금"],
    "short_term_fin": ["단기금융상품", "기타유동금융자산", "기타유동금융자산(단기금융상품)"],
    "short_term_debt": ["단기차입금", "단기차입부채", "차입부채"],
    "long_term_debt": ["장기차입금", "장기차입부채"],
}

IS_ACCOUNT_MAP = {
    "revenue": ["매출액", "수익", "영업수익", "매출"],
    "operating_income": ["영업이익", "영업손익", "영업이익(손실)"],
    "net_income": [
        "지배기업의소유주에게귀속되는당기순이익", "지배기업소유주에게귀속되는당기순이익",
        "지배주주순이익", "지배주주순이익(손실)",
        "당기순이익", "당기순이익(손실)",
        "분기순이익", "반기순이익", "연결당기순이익",
        "계속영업순이익"
    ],
    "depreciation": ["감가상각비", "유형자산감가상각비", "감가상각"],
    "amortization": ["무형자산상각비", "상각비"],
}

CF_ACCOUNT_MAP = {
    "cfo": [
        "영업활동으로인한현금흐름", "영업활동현금흐름",
        "영업활동으로인한순현금흐름", "영업활동현금흐름합계",
        "영업활동순현금흐름", "영업활동으로부터의현금흐름"
    ],
    "capex_ppe": ["유형자산의취득", "유형자산취득"],
    "capex_intangible": ["무형자산의취득", "무형자산취득", "사용권자산의취득"],
}

QUARTER_TO_REPRT = {"Q1": "11013", "Q2": "11012", "Q3": "11014", "Q4": "11011"}

REPRT_ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}

FINAL_COLS = [
    "기업종목코드","종목명","year","reprt_code",
    "revenue","revenue_growth","operating_income","operating_margin","net_income",
    "depreciation","ebitda",
    "equity","assets","liabilities","cash",
    "roe","roa","debt_ratio",
    "cfo","capex","fcf",
    "end_date","price","shares","market_cap","per","pbr","ev","ev_ebitda"
]

# 1) 공통 유틸
def to_number(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip()
    if s in ("", "-", "nan", "None"):
        return np.nan

    neg = False
    if re.match(r"^\(.*\)$", s):
        neg = True
        s = s[1:-1]

    s = s.replace(",", "").replace(" ", "")
    if s.startswith("-"):
        neg = True
        s = s[1:]
    if s.startswith("+"):
        s = s[1:]

    try:
        v = float(s)
        return -v if neg else v
    except Exception:
        return np.nan

def normalize_name(s):
    if pd.isna(s):
        return ""
    s = str(s)
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^\s*([0-9]+[\.\)]\s*)+", "", s)
    s = re.sub(r"^\s*([IVX]+|[Ⅰ-Ⅻ]+|[ⅰ-ⅻ]+)[\.\)]\s*", "", s)
    s = re.sub(r"^[\s\.\-·•]+", "", s)
    s = s.replace(" ", "").replace("손실", "")
    return s

def ensure_norm(df):
    df = df.copy()
    if "account_nm_norm" not in df.columns:
        df["account_nm_norm"] = df["account_nm"].apply(normalize_name)
    return df

def pick_amount(df, names, col, how="first"):
    if df is None or df.empty or col not in df.columns:
        return np.nan

    df = ensure_norm(df)
    pat = "|".join(re.escape(normalize_name(x)) for x in names)
    m = df[df["account_nm_norm"].str.contains(pat, na=False)].copy()
    if m.empty:
        return np.nan

    s = m[col].apply(to_number).astype(float)
    s = s[s.notna()]
    if s.empty:
        return np.nan

    if how == "sum":
        return float(s.sum())
    if how == "maxabs":
        return float(s.loc[s.abs().idxmax()])
    return float(s.iloc[0])

def get_fs_all(dart, stock_code, year, reprt_code):
    stock_code = str(stock_code).zfill(6)
    rc = str(reprt_code)

    fs = dart.finstate_all(stock_code, year, rc, fs_div="CFS")
    if isinstance(fs, pd.DataFrame) and not fs.empty:
        return fs, "CFS"

    fs = dart.finstate_all(stock_code, year, rc, fs_div="OFS")
    if isinstance(fs, pd.DataFrame) and not fs.empty:
        return fs, "OFS"

    return None, "-"

def reprt_to_end_date(year: int, reprt_code: str) -> str:
    return {
        "11013": f"{year}-03-31",
        "11012": f"{year}-06-30",
        "11014": f"{year}-09-30",
        "11011": f"{year}-12-31",
    }.get(str(reprt_code))

# 2) 원천 DF 만들기 (BS / IS / CF)
def build_bs_df(dart, stock_code, start_year=2023, end_year=2025, end_q="Q3"):
    rows, qs = [], ["Q1","Q2","Q3","Q4"]
    for year in range(start_year, end_year + 1):
        for q in qs:
            if year == end_year and qs.index(q) > qs.index(end_q):
                break
            rc = QUARTER_TO_REPRT[q]
            fs, used = get_fs_all(dart, stock_code, year, rc)

            row = {"year": year, "reprt_code": rc, "fs_div": used}
            if fs is None:
                for k in BS_ACCOUNT_MAP.keys():
                    row[k] = np.nan
                rows.append(row)
                continue

            bs = fs[fs["sj_div"] == "BS"].copy()
            for k, names in BS_ACCOUNT_MAP.items():
                row[k] = pick_amount(bs, names, "thstrm_amount", how="maxabs")
            rows.append(row)

    return pd.DataFrame(rows)

def build_is_df(dart, stock_code, start_year=2023, end_year=2025, end_q="Q3"):
    rows, qs = [], ["Q1","Q2","Q3","Q4"]
    for year in range(start_year, end_year + 1):
        for q in qs:
            if year == end_year and qs.index(q) > qs.index(end_q):
                break
            rc = QUARTER_TO_REPRT[q]
            fs, used = get_fs_all(dart, stock_code, year, rc)

            row = {"year": year, "reprt_code": rc, "fs_div": used}
            if fs is None:
                for k in IS_ACCOUNT_MAP.keys():
                    row[f"{k}_amount"] = np.nan
                    row[f"{k}_add_amount"] = np.nan
                rows.append(row)
                continue

            is_df = fs[fs["sj_div"].isin(["IS","CIS"])].copy()
            for k, names in IS_ACCOUNT_MAP.items():
                how = "sum" if k in ("depreciation","amortization") else "maxabs"
                row[f"{k}_amount"] = pick_amount(is_df, names, "thstrm_amount", how=how)
                row[f"{k}_add_amount"] = pick_amount(is_df, names, "thstrm_add_amount", how=how)

            rows.append(row)

    return pd.DataFrame(rows)

def build_cf_df(dart, stock_code, start_year=2023, end_year=2025, end_q="Q3"):
    rows, qs = [], ["Q1","Q2","Q3","Q4"]
    for year in range(start_year, end_year + 1):
        for q in qs:
            if year == end_year and qs.index(q) > qs.index(end_q):
                break
            rc = QUARTER_TO_REPRT[q]
            fs, used = get_fs_all(dart, stock_code, year, rc)

            row = {"year": year, "reprt_code": rc, "fs_div": used}
            if fs is None:
                row["cfo_amount"] = np.nan
                row["capex_ppe_amount"] = np.nan
                row["capex_intangible_amount"] = np.nan
                rows.append(row)
                continue

            cf = fs[fs["sj_div"] == "CF"].copy()
            row["cfo_amount"] = pick_amount(cf, CF_ACCOUNT_MAP["cfo"], "thstrm_amount", how="maxabs")
            row["capex_ppe_amount"] = pick_amount(cf, CF_ACCOUNT_MAP["capex_ppe"], "thstrm_amount", how="sum")
            row["capex_intangible_amount"] = pick_amount(cf, CF_ACCOUNT_MAP["capex_intangible"], "thstrm_amount", how="sum")

            rows.append(row)

    return pd.DataFrame(rows)

# 3) 누적 -> 분기 차분 (reprt_code만 사용)
def normalize_is(is_df: pd.DataFrame) -> pd.DataFrame:
    df = is_df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["reprt_code"] = df["reprt_code"].astype(str)
    df["rc_order"] = df["reprt_code"].map(REPRT_ORDER)

    df = df.sort_values(["year", "rc_order"]).reset_index(drop=True)

    needed = {
        "revenue": ("revenue_amount", "revenue_add_amount"),
        "operating_income": ("operating_income_amount", "operating_income_add_amount"),
        "net_income": ("net_income_amount", "net_income_add_amount"),
        "depreciation": ("depreciation_amount", "depreciation_add_amount"),
        "amortization": ("amortization_amount", "amortization_add_amount"),
    }

    for k,(a_col, add_col) in needed.items():
        if a_col in df.columns: df[a_col] = pd.to_numeric(df[a_col], errors="coerce")
        if add_col in df.columns: df[add_col] = pd.to_numeric(df[add_col], errors="coerce")

    out = df[["year","reprt_code","fs_div"]].copy()

    for k,(a_col, add_col) in needed.items():
        a = df[a_col] if a_col in df.columns else np.nan
        add = df[add_col] if add_col in df.columns else np.nan

        # 누적 선택 규칙: Q1/Q4=amount, Q2/Q3=add
        is_q1_or_q4 = df["reprt_code"].isin(["11013", "11011"])
        cum = np.where(is_q1_or_q4, a, add)
        cum = pd.Series(cum, index=df.index)

        prev_cum = cum.groupby(df["year"]).shift(1)
        is_q1 = df["reprt_code"].eq("11013")
        q_val = np.where(is_q1, cum, cum - prev_cum)

        out[k] = q_val

    return out

def normalize_cf(cf_df: pd.DataFrame) -> pd.DataFrame:
    df = cf_df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["reprt_code"] = df["reprt_code"].astype(str)
    df["rc_order"] = df["reprt_code"].map(REPRT_ORDER)

    df = df.sort_values(["year", "rc_order"]).reset_index(drop=True)

    df["cfo_amount"] = pd.to_numeric(df["cfo_amount"], errors="coerce")
    df["capex_ppe_amount"] = pd.to_numeric(df["capex_ppe_amount"], errors="coerce")
    df["capex_intangible_amount"] = pd.to_numeric(df["capex_intangible_amount"], errors="coerce")

    df["capex_total_amount"] = (df["capex_ppe_amount"].fillna(0) + df["capex_intangible_amount"].fillna(0)).abs()

    cum_cfo = df["cfo_amount"]
    cum_capex = df["capex_total_amount"]

    prev_cfo = cum_cfo.groupby(df["year"]).shift(1)
    prev_capex = cum_capex.groupby(df["year"]).shift(1)

    is_q1 = df["reprt_code"].eq("11013")
    df["cfo"] = np.where(is_q1, cum_cfo, cum_cfo - prev_cfo)
    df["capex"] = np.where(is_q1, cum_capex, cum_capex - prev_capex)

    df["fcf"] = df["cfo"] - df["capex"]

    return df[["year","reprt_code","fs_div","cfo","capex","fcf"]]

# 4) Price/Shares
def get_price_and_shares(stock_code: str, year_list, reprt_codes, buffer_days: int = 30) -> pd.DataFrame:
    krx = fdr.StockListing("KRX").copy()
    krx["Code_norm"] = krx["Code"].astype(str).str.zfill(6)

    row = krx[krx["Code_norm"] == str(stock_code).zfill(6)]
    shares = np.nan if row.empty else float(str(row.iloc[0]["Stocks"]).replace(",", ""))

    rows = []
    for year in year_list:
        for rc in reprt_codes:
            end_date = reprt_to_end_date(int(year), str(rc))
            if end_date is None:
                continue

            start_date = (pd.to_datetime(end_date) - pd.Timedelta(days=buffer_days)).strftime("%Y-%m-%d")
            try:
                df = fdr.DataReader(stock_code, start_date, end_date)
                price = np.nan if df.empty else float(df["Close"].iloc[-1])
            except Exception:
                price = np.nan

            rows.append({
                "year": int(year),
                "reprt_code": str(rc),
                "end_date": end_date,
                "price": price,
                "shares": shares,
            })

    p = pd.DataFrame(rows)
    p["market_cap"] = p["price"] * p["shares"]
    return p[["year","reprt_code","end_date","price","shares","market_cap"]]

# 5) FINAL
def build_final_df(
    dart,
    stock_code: str,
    stock_name: str,
    start_year=2023,
    end_year=2025,
    end_q="Q3",
):
    stock_code = str(stock_code).zfill(6)

    bs_df = build_bs_df(dart, stock_code, start_year, end_year, end_q)
    is_df = build_is_df(dart, stock_code, start_year, end_year, end_q)
    cf_df = build_cf_df(dart, stock_code, start_year, end_year, end_q)

    # BS 숫자화
    bs = bs_df.copy()
    for c in ["assets","cash","liabilities","equity","short_term_debt","long_term_debt"]:
        if c in bs.columns:
            bs[c] = pd.to_numeric(bs[c], errors="coerce")

    is_q = normalize_is(is_df)
    cf_q = normalize_cf(cf_df)

    years = list(range(start_year, end_year + 1))
    price_df = get_price_and_shares(stock_code, years, ["11013","11012","11014","11011"])

    base = (
        bs.merge(is_q, on=["year","reprt_code","fs_div"], how="outer")
          .merge(cf_q, on=["year","reprt_code","fs_div"], how="outer")
          .merge(price_df, on=["year","reprt_code"], how="left")
    ).sort_values(["year","reprt_code"]).reset_index(drop=True)

    base["기업종목코드"] = stock_code
    base["종목명"] = stock_name

    # 파생
    base["operating_margin"] = base["operating_income"] / base["revenue"]
    base["debt_ratio"] = base["liabilities"] / base["equity"]
    base["roe"] = base["net_income"] / base["equity"]
    base["roa"] = base["net_income"] / base["assets"]

    # YoY (같은 reprt_code끼리 1년 전 비교)
    base["revenue_growth"] = base["revenue"] / base.groupby(["기업종목코드","reprt_code"])["revenue"].shift(1) - 1

    base["depreciation"] = pd.to_numeric(base.get("depreciation", np.nan), errors="coerce")
    base["amortization"] = pd.to_numeric(base.get("amortization", np.nan), errors="coerce")
    base["ebitda"] = base["operating_income"] + base["depreciation"].fillna(0) + base["amortization"].fillna(0)

    # EV 계산용 debt_total
    if "short_term_debt" in base.columns and "long_term_debt" in base.columns:
        debt_total = base["short_term_debt"].fillna(0) + base["long_term_debt"].fillna(0)
    elif "short_term_debt" in base.columns:
        debt_total = base["short_term_debt"].fillna(0)
    elif "long_term_debt" in base.columns:
        debt_total = base["long_term_debt"].fillna(0)
    else:
        debt_total = 0

    base["ev"] = base["market_cap"] + debt_total - base["cash"]

    base["per"] = base["market_cap"] / base["net_income"]
    base["pbr"] = base["market_cap"] / base["equity"]
    base["ev_ebitda"] = base["ev"] / base["ebitda"]

    # 최종 컬럼 보강
    for c in FINAL_COLS:
        if c not in base.columns:
            base[c] = np.nan

    return base[FINAL_COLS].copy()




OUT_DIR = Path(".")
FIN_DIR = OUT_DIR / "fin_"
FIN_DIR.mkdir(parents=True, exist_ok=True)

KEYS = ["기업종목코드", "year", "reprt_code"]

REPRT_TO_Q = {v: k for k, v in QUARTER_TO_REPRT.items()}

def normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df["기업종목코드"] = df["기업종목코드"].astype(str).str.strip().str.zfill(6)
    df["year"] = df["year"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["reprt_code"] = df["reprt_code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return df

def upsert_df(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    inc = normalize_keys(incoming)
    if existing is None or existing.empty:
        return inc.copy()

    ex = normalize_keys(existing)
    ex["_src"] = 0
    inc["_src"] = 1

    combined = pd.concat([ex, inc], ignore_index=True)
    combined = (
        combined.sort_values(KEYS + ["_src"])
                .drop_duplicates(subset=KEYS, keep="last")
                .drop(columns=["_src"])
    )
    return combined

def chunk_list(lst, size=20):
    for i in range(0, len(lst), size):
        yield lst[i:i+size], i//size + 1

def run_batch(dart, corp_batch, start_year, end_year, end_q, include_prev_year=False):
    results = []

    for stock_code, stock_name in corp_batch:
        stock_code6 = str(stock_code).zfill(6)
        print(f"▶ {stock_code6} {stock_name}")

        try:
            calc_start_year = start_year - 1 if include_prev_year else start_year

            df = build_final_df(
                dart=dart,
                stock_code=stock_code6,
                stock_name=stock_name,
                start_year=calc_start_year,
                end_year=end_year,
                end_q=end_q,
            )

            df["year"] = pd.to_numeric(df["year"], errors="coerce")
            df = df[df["year"] >= start_year].copy()

            results.append(df)

        except Exception as e:
            print(f"  [ERROR] {stock_code6} {stock_name} -> {type(e).__name__}: {e}")

    batch_df = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    return batch_df

def save_batch(batch_df: pd.DataFrame, fin_dir: Path = FIN_DIR):
    if batch_df is None or batch_df.empty:
        return

    df = batch_df.copy()

    # 키 정규화 + quarter 생성
    df = normalize_keys(df)
    df["quarter"] = df["reprt_code"].map(REPRT_TO_Q)
    df = df[df["quarter"].notna()].copy()

    df["year_int"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df[df["year_int"].notna()].copy()

    # 분기별 파일 업서트
    for (y, q), g in df.groupby(["year_int", "quarter"], dropna=True):
        out_path = fin_dir / f"fin_{int(y)}_{q}.csv"

        g = g.drop(columns=["quarter", "year_int"])

        if out_path.exists():
            ex = pd.read_csv(out_path, dtype=str)
            merged = upsert_df(ex, g)
        else:
            merged = normalize_keys(g)

        merged.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f" saved: {out_path.name} (rows={len(merged)})")

def run_batches(
    dart,
    csv_path,
    start_year,
    end_year,
    end_q,
    chunk_size=20,
    include_prev_year=False,
    fin_dir: Path = FIN_DIR,
):
    fin_dir.mkdir(parents=True, exist_ok=True)

    kospi = pd.read_csv(csv_path, dtype=str)
    kospi["기업종목코드"] = kospi["기업종목코드"].str.strip().str.zfill(6)
    kospi["종목명"] = kospi["종목명"].str.strip()

    corp_list = list(zip(kospi["기업종목코드"], kospi["종목명"]))


    for batch, idx in chunk_list(corp_list, chunk_size):
        batch_df = run_batch(
            dart, batch, start_year, end_year, end_q,
            include_prev_year=include_prev_year
        )

        if batch_df.empty:
            print(f"Batch {idx}: 저장할 결과가 없음")
            continue

        save_batch(batch_df, fin_dir=fin_dir)

    print(" 전체 배치 완료 ")


run_batches(
    dart=dart,
    csv_path = "KOSPI200.csv",
    start_year=2023,
    end_year=2025,
    end_q="Q3",
    chunk_size=20,
    include_prev_year=True
)

