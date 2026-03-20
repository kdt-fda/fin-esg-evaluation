###############################################################
# 당일 뉴스 → 클렌징 → FinBERT → 종목코드 매핑 → DB 적재
###############################################################

import re
import hashlib
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
import requests
from bs4 import BeautifulSoup
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import time
from pykrx import stock

import os
import pymysql
from dotenv import load_dotenv
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
        database=db_name,
        charset='utf8mb4'
    )
    return conn

HEADERS = {"User-Agent": "Mozilla/5.0"}
MODEL_NAME = "snunlp/KR-FinBert-SC"
BATCH_SIZE = 32
MAX_LEN = 512

###############################################################
# 진행상황 출력용 (멀티스레드 안전)
###############################################################
print_lock = threading.Lock()
total_articles_collected = 0

def log(msg):
    with print_lock:
        print(msg, flush=True)

###############################################################
# 1️⃣ 클렌징
###############################################################

RE_URL   = re.compile(r'(https?://\S+|www\.\S+)', re.IGNORECASE)
RE_EMAIL = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
RE_PHONE = re.compile(r'(\+?\d[\d\- ]{7,}\d)')
RE_SOURCE_EQ = re.compile(r'(\(|\[)\s*[^()\[\]]{0,30}\s*=\s*[^()\[\]]{0,30}\s*(\)|\])')
RE_SOURCE_END = re.compile(r'(\(|\[|【)\s*[가-힣A-Za-z·\s]{1,30}\s*(=)?\s*[가-힣A-Za-z0-9·\s]{0,30}\s*(\)|\]|】)\s*$')
RE_SOURCE_LINE = re.compile(r'^\s*(\(|\[|【)\s*[가-힣A-Za-z·\s]{1,30}\s*(=)?\s*[가-힣A-Za-z0-9·\s]{0,30}\s*(\)|\]|】)\s*$', re.MULTILINE)
RE_REPORTER = re.compile(r'([가-힣]{2,4}\s*(기자|특파원|선임기자|수습기자))')
RE_INPUT    = re.compile(r'(입력|수정)\s*\d{4}\.\d{2}\.\d{2}.*$', re.MULTILINE)
RE_COPYRIGHT = re.compile(r'(무단전재|재배포\s*금지|전재\s*금지|ⓒ|Copyright)', re.IGNORECASE)
RE_BULLETS  = re.compile(r'[△▽◇◆■□●○◎※▶▷◀◁•▪]')
RE_KEEP = re.compile(r'[^0-9A-Za-z가-힣\s\.\,\?\!\-\%\+\/]')
RE_SPACE = re.compile(r'\s+')

def clean_text(s):
    s = (s or "").strip()
    if not s:
        return ""

    s = RE_URL.sub(" ", s)
    s = RE_EMAIL.sub(" ", s)
    s = RE_PHONE.sub(" ", s)
    s = RE_SOURCE_EQ.sub(" ", s)
    s = RE_SOURCE_LINE.sub(" ", s)
    s = RE_SOURCE_END.sub(" ", s)
    s = RE_REPORTER.sub(" ", s)
    s = RE_INPUT.sub(" ", s)

    lines=[]
    for line in s.splitlines():
        if RE_COPYRIGHT.search(line):
            continue
        lines.append(line)
    s="\n".join(lines)

    s = RE_BULLETS.sub(" ", s)
    s = RE_KEEP.sub(" ", s)
    s = RE_SPACE.sub(" ", s).strip()
    return s

def make_hash(company, date, text):
    return hashlib.md5(f"{company}|{date}|{text[:800]}".encode()).hexdigest()

def norm_name(x):
    """종목명에서 공백과 특수문자를 제거하여 매핑 정확도를 높임"""
    x = str(x)
    x = re.sub(r"\s+", "", x) # 모든 공백 제거
    x = re.sub(r"[()·\-\.\,]", "", x) # 주요 특수문자 제거
    return x

###############################################################
# 2️⃣ 종목코드 로드
###############################################################

def load_company_mapping_from_db():
    """DB의 KOSPI200_STOCKS_TB에서 종목명과 코드를 가져와 매핑 딕셔너리 생성"""
    conn = _connect()
    try:
        # DictCursor를 사용하여 컬럼명으로 접근
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # 종목 매핑 정보 조회
            cur.execute("SELECT ticker, stock_name FROM KOSPI200_STOCKS_TB WHERE is_active = TRUE")
            rows = cur.fetchall()
            mapping = {norm_name(r['stock_name']): r['ticker'] for r in rows}
            companies = [r['stock_name'] for r in rows]

            # 마지막 수집 날짜 확인
            cur.execute("SELECT MAX(trade_date) as last_date FROM NEWS_TB")
            last_date = cur.fetchone()['last_date']
            today = dt.date.today()

            # 마지막 수집일이 어제거나 오늘인 경우
            if last_date >= (today - dt.timedelta(days=1)):
                start_date = today
            else:
                # 마지막 수집일이 어제보다 더 과거인 경우
                start_date = last_date + dt.timedelta(days=1)

            end_date = today
            
            log(f"✅ DB에서 {len(companies)}개 종목 로드 완료")
            log(f"📅 DB 마지막 기록: {last_date}")
            log(f"✅ 수집 범위: {start_date} ~ {end_date}")
            return mapping, companies, start_date, end_date

    finally:
        conn.close()

###############################################################
# 3️⃣ 동아일보
###############################################################

def crawl_donga(company, target_date, idx, total):
    rows=[]
    t_str = target_date.strftime("%Y-%m-%d")
    try:
        url=f"https://www.donga.com/news/search?query={company}&sorting=2"
        res=requests.get(url,headers=HEADERS,timeout=10)
        soup=BeautifulSoup(res.text,"html.parser")
        links=[a['href'] for a in soup.select("h4 a")]

        for link in links[:5]:
            r=requests.get(link,headers=HEADERS,timeout=10)
            s=BeautifulSoup(r.text,"html.parser")
            body=s.find("div",id="article_txt")
            if not body: continue
            text=clean_text(body.get_text(" ",strip=True))
            if len(text)<80: continue
            rows.append([company, t_str, text])

        log(f"[{idx}/{total}] {company} - 동아일보 완료 ({len(rows)}건)")
    except Exception as e:
        log(f"[{idx}/{total}] {company} - 동아일보 실패")

    return rows

###############################################################
# 4️⃣ 조선일보
###############################################################

def crawl_chosun(company, target_date, idx, total):
    rows=[]
    t_str = target_date.strftime("%Y-%m-%d")
    try:
        url=f"https://search.chosun.com/search/news.search?query={company}&orderby=news"
        res=requests.get(url,headers=HEADERS,timeout=10)
        soup=BeautifulSoup(res.text,"html.parser")
        links=[a['href'] for a in soup.select("dl.search_news a")]

        for link in links[:5]:
            r=requests.get(link,headers=HEADERS,timeout=10)
            s=BeautifulSoup(r.text,"html.parser")
            body=s.find("article")
            if not body: continue
            text=clean_text(body.get_text(" ",strip=True))
            if len(text)<80: continue
            rows.append([company, t_str, text])

        log(f"[{idx}/{total}] {company} - 조선일보 완료 ({len(rows)}건)")
    except:
        log(f"[{idx}/{total}] {company} - 조선일보 실패")

    return rows

###############################################################
# 5️⃣ 한국경제
###############################################################

def crawl_hankyung(company, target_date, idx, total):
    rows=[]
    t_dot = target_date.strftime("%Y.%m.%d")
    t_str = target_date.strftime("%Y-%m-%d")
    try:
        url=f"https://search.hankyung.com/search/news?query={company}&sort=DATE/DESC&period=DATE&sdate={t_dot}&edate={t_dot}"
        res=requests.get(url,headers=HEADERS,timeout=10)
        soup=BeautifulSoup(res.text,"html.parser")
        links=[a['href'] for a in soup.select("ul.article li div.txt_wrap a")]

        for link in links[:5]:
            r=requests.get(link,headers=HEADERS,timeout=10)
            s=BeautifulSoup(r.text,"html.parser")
            body=s.select_one("#articletxt")
            if not body: continue
            text=clean_text(body.get_text(" ",strip=True))
            if len(text)<80: continue
            rows.append([company, t_str, text])

        log(f"[{idx}/{total}] {company} - 한국경제 완료 ({len(rows)}건)")
    except:
        log(f"[{idx}/{total}] {company} - 한국경제 실패")

    return rows

###############################################################
# 6️⃣ 분석 및 DB 적재
###############################################################

@torch.no_grad()
def score_news(df):

    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer=AutoTokenizer.from_pretrained(MODEL_NAME)
    model=AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(device)
    model.eval()

    texts=df["text"].tolist()
    scores=[]

    for i in range(0,len(texts),BATCH_SIZE):
        batch=texts[i:i+BATCH_SIZE]
        enc=tokenizer(batch,padding=True,truncation=True,max_length=MAX_LEN,return_tensors="pt").to(device)
        logits=model(**enc).logits
        prob=torch.softmax(logits,dim=1)
        score=(prob[:,2]-prob[:,0]).cpu().numpy()
        scores.extend(score)

        print(f"FinBERT 처리: {min(i+BATCH_SIZE,len(texts))}/{len(texts)}", flush=True)

    df["score"]=scores
    return df

def upload_news_score_to_db(df_in):
    if df_in.empty: return

    # 1. 실제 거래일 리스트
    start_str = "20230101"
    future_str = (dt.date.today() + dt.timedelta(days=10)).strftime("%Y%m%d")

    market_days = stock.get_previous_business_days(fromdate=start_str, todate=future_str)
    market_days_series = pd.Series(market_days)

    # 2. 날짜 조정 함수
    def get_next_trading_day(target_date):
        target_date = pd.to_datetime(target_date)

        # 수집된 뉴스 날짜보다 크거나 같은 실제 영업일만 달력에서 필터링
        future_days = market_days_series[market_days_series >= target_date]
        if not future_days.empty:
            return future_days.iloc[0]
        return target_date # 미래 거래일이 없으면 일단 그대로 반환
    
    # 3. 뉴스 날짜를 다음 '실제 거래일'로 변환
    df_in['date'] = pd.to_datetime(df_in['date'])
    df_in['trade_date'] = df_in['date'].apply(get_next_trading_day)

    # 4. 종목별/날짜별 집계 (평균 점수와 기사 수 동시 계산)
    final = df_in.groupby(["company", "종목코드", "trade_date"]).agg(
        점수=('score', 'mean'),
        기사수=('score', 'count')
    ).reset_index()

    final.rename(columns={'company': '기업명', 'trade_date': '날짜'}, inplace=True)
    
    # 5. DB 적재 (가중 평균 누적)
    conn = _connect()
    try:
        cur = conn.cursor()
        data_list = []
        for _, row in final.iterrows():
            data_list.append((
                row['날짜'], 
                row['종목코드'], 
                row['기업명'], 
                float(row['점수']), 
                int(row['기사수'])
            ))

        sql = """
            INSERT INTO NEWS_TB (trade_date, ticker, stock_name, score, article_count)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                score = ((score * article_count) + (VALUES(score) * VALUES(article_count))) / (article_count + VALUES(article_count)),
                article_count = article_count + VALUES(article_count);
        """
        
        if data_list:
            cur.executemany(sql, data_list)
            conn.commit()
            log(f"✅ DB 적재 완료: {len(data_list)}건")
            
    except Exception as e:
        conn.rollback()
        log(f"❌ DB 적재 에러: {e}")
    finally:
        conn.close()

###############################################################
# 7️⃣ 메인 프로세서 실행 (모듈화)
###############################################################

def run_news_processor():
    log("🚀 뉴스 프로세서 시작")
    
    # 1. 매핑 및 기간 설정 로드
    mapping, companies, start_date, end_date = load_company_mapping_from_db()

    if start_date > end_date:
        log("✅ 이미 오늘까지의 데이터가 최신 상태입니다. 종료합니다.")
        return

    date_range = [start_date + dt.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    log(f"📅 {start_date} ~ {end_date} 기간 데이터 수집 시작 (총 {len(date_range)}일분)")

    all_rows=[]
    seen=set()
    total=len(companies)

    # 2. 크롤링 실행
    for target_dt in date_range:
        log(f"🔎 {target_dt.strftime('%Y-%m-%d')} 뉴스 수집 중...")
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures=[]
            for idx, c in enumerate(companies, 1):
                futures.append(ex.submit(crawl_donga, c, target_dt, idx, total))
                futures.append(ex.submit(crawl_chosun, c, target_dt, idx, total))
                futures.append(ex.submit(crawl_hankyung, c, target_dt, idx, total))

            for f in as_completed(futures):
                for row in f.result():
                    h=make_hash(row[0], row[1], row[2])
                    if h in seen: continue
                    seen.add(h)
                    all_rows.append(row)
        time.sleep(1) # IP 차단 방지

    if not all_rows:
        log("⚠️ 수집된 데이터가 없습니다.")
        return

    df=pd.DataFrame(all_rows,columns=["company","date","text"])
    log(f"총 수집 기사수: {len(df)}")

    # 3. FinBERT 분석 및 매핑
    df=score_news(df)
    df["norm"] = df["company"].apply(norm_name)
    df["종목코드"] = df["norm"].map(mapping)

    # 매핑되지 않은 종목 제외
    before_len = len(df)
    df = df.dropna(subset=["종목코드"])
    if before_len > len(df):
        log(f"⚠️ 매핑 실패한 {before_len - len(df)}건 제외")

    # 4. DB 적재
    if not df.empty:
        upload_news_score_to_db(df)
    else:
        log("⚠️ 적재할 데이터가 없습니다.")

    log("🏁 뉴스 프로세서 완료")

if __name__ == "__main__":
    run_news_processor()