import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from concurrent.futures import ThreadPoolExecutor

# =========================
# 설정
# =========================
headers = {"User-Agent": "Mozilla/5.0"}

FUND_PATH = "fundamental_2025_Q1.csv"
NAME_COL  = "종목명"

START_DATE = "2023.01.01"
END_DATE   = "2025.12.31"

MAX_PER_DAY = 5
MAX_WORKERS = 10

OUT_ALL = "hankyung_news_2023_2025.csv"
OUT_DIR_PREFIX = "hankyung_news_"

BASE_SEARCH_URL = (
    "https://search.hankyung.com/search/news"
    "?query={query}"
    "&sort=DATE%2FDESC%2CRANK%2FDESC"
    "&period=DATE"
    "&area=ALL"
    f"&sdate={START_DATE}"
    f"&edate={END_DATE}"
    "&exact=&include=&except=&hk_only=n"
)

# =========================
# 유틸
# =========================
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()[:200]

def normalize_date(text: str) -> str:
    return text[:10].replace(".", "-") if text else "날짜 없음"

# =========================
# 기사 본문 수집 (원래 코드 유지)
# =========================
def fetch_article(url):
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        date_elem = soup.select_one("span.txt-date")
        date_text = normalize_date(date_elem.get_text(strip=True) if date_elem else "")

        title_elem = soup.select_one("h1.headline")
        title = title_elem.get_text(strip=True) if title_elem else "제목 없음"

        body_elem = soup.select_one("#articletxt")
        content = body_elem.get_text(" ", strip=True) if body_elem else "본문 없음"

        return [date_text, f"{title}\n\n{content}"]

    except Exception:
        return None

# =========================
# 기업 1개 크롤링
# =========================
def crawl_one_company(company):
    query = requests.utils.quote(company)
    page = 1
    rows = []

    while True:
        search_url = BASE_SEARCH_URL.format(query=query) + f"&page={page}"

        try:
            res = requests.get(search_url, headers=headers, timeout=10)
            res.encoding = "utf-8"
            soup = BeautifulSoup(res.text, "html.parser")

            articles = soup.select("ul.article > li div.txt_wrap > a")
            if not articles:
                break

            urls = [a["href"] for a in articles if a.get("href")]

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                results = list(executor.map(fetch_article, urls))

            rows.extend([r for r in results if r])

            page += 1
            time.sleep(0.3)

        except Exception:
            page += 1
            continue

    df = pd.DataFrame(rows, columns=["date", "full_text"])
    if df.empty:
        return pd.DataFrame(columns=["company", "date", "full_text"])

    # 날짜 정리
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_dt"])
    df = df.sort_values("date_dt")

    # 날짜별 최대 N개
    df = df.groupby("date_dt", as_index=False).head(MAX_PER_DAY)

    df["date"] = df["date_dt"].dt.strftime("%Y-%m-%d")
    df = df.drop(columns="date_dt")

    df.insert(0, "company", company)
    df["full_text"] = df["full_text"].str.replace(r"[\n\r]+", "\n", regex=True).str.strip()
    df = df.drop_duplicates(subset=["full_text"]).reset_index(drop=True)

    return df

# =========================
# 메인
# =========================
if __name__ == "__main__":
    fund = pd.read_csv(FUND_PATH, encoding="utf-8-sig")

    companies = (
        fund[NAME_COL]
        .dropna()
        .astype(str)
        .str.strip()
        .drop_duplicates()
        .tolist()
    )

    print(f"✅ 기업 수: {len(companies)}")

    all_frames = []

    for i, company in enumerate(companies, start=1):
        print(f"\n[{i}/{len(companies)}] ▶ {company} 수집 시작")

        df_company = crawl_one_company(company)
        print(f"   → {len(df_company)}건 수집")

        out_path = f"{OUT_DIR_PREFIX}{safe_filename(company)}.csv"
        df_company.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"   → 저장 완료: {out_path}")

        all_frames.append(df_company)
        time.sleep(0.2)

    df_all = pd.concat(all_frames, ignore_index=True)
    df_all.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    print(f"\n✅ 전체 통합 저장 완료: {OUT_ALL} (총 {len(df_all)}건)")
