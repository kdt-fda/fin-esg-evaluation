import pandas as pd
import hashlib

DONGA    = "donga_cleansing.csv"
HANKYUNG = "hankyung_cleansing.csv"
CHOSUN   = "chosun_cleansing.csv"

OUTFILE  = "news.csv"

def make_hash(company, date, text):
    key = f"{company}|{date}|{text[:800]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()

# 로드
df_donga    = pd.read_csv(DONGA, encoding="utf-8-sig")
df_hankyung = pd.read_csv(HANKYUNG, encoding="utf-8-sig")
df_chosun   = pd.read_csv(CHOSUN, encoding="utf-8-sig")

# 단순 결합
news = pd.concat([df_donga, df_hankyung, df_chosun], ignore_index=True)

# 중복 제거
news["hash"] = news.apply(
    lambda r: make_hash(r["company"], r["date"], r["full_text"]),
    axis=1
)
news = news.drop_duplicates(subset=["hash"]).reset_index(drop=True)

# 날짜 타입 변환
news["date"] = pd.to_datetime(news["date"], errors="coerce")

# 기업명 오름차순 + 날짜 내림차순 정렬
news = news.sort_values(
    by=["company", "date"],
    ascending=[True, False]
).reset_index(drop=True)

# 컬럼 정리
news = news[["company", "date", "full_text"]]

# 저장
news.to_csv(OUTFILE, index=False, encoding="utf-8-sig")

print("✅ saved:", OUTFILE)
print("총 행 수:", len(news))
