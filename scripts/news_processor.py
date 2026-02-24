import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re
import time
import hashlib
import torch
import pymysql
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from dotenv import load_dotenv

# ============================================================
# 1. 설정 및 로드
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

MODEL_NAME = "snunlp/KR-FinBert-SC"
BATCH_SIZE = 32
MAX_LEN = 256
MAX_PER_DAY = 5  # 하루 최대 수집 기사 수
headers = {"User-Agent": "Mozilla/5.0"}

# 수집 기간 설정 (어제부터 오늘까지 자동화용, 혹은 수동 설정)
END_DATE = datetime.now().strftime("%Y.%m.%d")
START_DATE = (datetime.now() - timedelta(days=1)).strftime("%Y.%m.%d")

# FinBERT 모델 로드
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(device)
model.eval()
label_values = torch.linspace(-1.0, 1.0, steps=int(model.config.num_labels), device=device)

# ============================================================
# 2. 유틸리티 및 클렌징 함수
# ============================================================
def clean_text(text):
    """기자명, 이메일, 광고성 문구 제거"""
    text = re.sub(r'[a-zA-Z0-9+-_.] + @[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', text) # 이메일 제거
    text = re.sub(r'\(.*?\)|\{.*?\}|\[.*?\]', '', text) # 괄호 안 문구(기자명 등) 제거
    text = re.sub(r'[^가-힣\s\d%]', ' ', text) # 한글, 숫자, % 제외 특수문자 제거
    return " ".join(text.split())

def fetch_article(url):
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        # 한경 기준 (필요시 동아, 조선 선택자 추가)
        title = soup.select_one("h1.headline").get_text(strip=True) if soup.select_one("h1.headline") else ""
        content = soup.select_one("#articletxt").get_text(" ", strip=True) if soup.select_one("#articletxt") else ""
        date_text = soup.select_one("span.txt-date").get_text(strip=True)[:10].replace(".", "-") if soup.select_one("span.txt-date") else ""
        return [date_text, f"{title} {content}"]
    except:
        return None

# ============================================================
# 3. 크롤링 및 수집 로직
# ============================================================
def crawl_company_news(company_name):
    query = requests.utils.quote(company_name)
    search_url = f"https://search.hankyung.com/search/news?query={query}&sort=DATE%2FDESC&period=DATE&sdate={START_DATE}&edate={END_DATE}"
    
    try:
        res = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        articles = soup.select("ul.article > li div.txt_wrap > a")
        urls = [a["href"] for a in articles[:15]] # 상위 15개 추출

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(fetch_article, urls))
        
        rows = [r for r in results if r and r[0]]
        df = pd.DataFrame(rows, columns=["date", "full_text"])
        df['company'] = company_name
        return df
    except:
        return pd.DataFrame()

# ============================================================
# 4. 점수화 (FinBERT)
# ============================================================
@torch.no_grad()
def get_sentiment_scores(texts):
    if not texts: return []
    enc = tokenizer(texts, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt").to(device)
    logits = model(**enc).logits
    probs = torch.softmax(logits, dim=-1)
    scores = (probs * label_values).sum(dim=-1)
    return scores.cpu().numpy()

# ============================================================
# 5. 메인 실행 함수 (run_news_processor)
# ============================================================
def run_news_processor():
    print(f"🚀 뉴스 감성 분석 파이프라인 시작 ({START_DATE} ~ {END_DATE})")
    
    # 1. DB에서 종목명 조회
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE is_active=TRUE")
            stocks = cur.fetchall() # (ticker, name) 튜플 리스트
    finally:
        conn.close()

    all_news_list = []
    for ticker, name in stocks:
        print(f"📡 {name}({ticker}) 뉴스 수집 중...")
        df_comp = crawl_company_news(name)
        if not df_comp.empty:
            df_comp['ticker'] = ticker
            all_news_list.append(df_comp)
        time.sleep(0.1)

    if not all_news_list:
        print("✅ 수집된 뉴스가 없습니다.")
        return

    full_df = pd.concat(all_news_list, ignore_index=True)
    
    # 2. 전처리 및 중복 제거
    full_df['full_text'] = full_df['full_text'].apply(clean_text)
    full_df = full_df.drop_duplicates(subset=['ticker', 'full_text'])
    
    # 3. 감성 점수 계산 (배치 처리)
    print(f"🧠 FinBERT 감성 분석 중... (총 {len(full_df)}건)")
    texts = full_df['full_text'].tolist()
    scores = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        scores.extend(get_sentiment_scores(batch))
    full_df['score'] = scores

    # 4. 일자별/종목별 평균 점수 산출
    final_df = full_df.groupby(['date', 'ticker'], as_index=False)['score'].mean()

    # 5. DB 적재
    print("💾 분석 결과 DB 적재 중...")
    conn = _connect()
    try:
        with conn.cursor() as cur:
            sql = """
                INSERT INTO NEWS_TB (trade_date, ticker, score)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE score = VALUES(score)
            """
            data = [(row['date'], row['ticker'], float(row['score'])) for _, row in final_df.iterrows()]
            cur.executemany(sql, data)
        conn.commit()
        print(f"✅ 완료! {len(final_df)}건의 점수가 업데이트되었습니다.")
    except Exception as e:
        print(f"❌ DB 에러: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_news_processor()