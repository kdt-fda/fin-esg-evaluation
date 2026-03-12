###############################################################
# 당일 뉴스 → 클렌징 → FinBERT → 종목코드 매핑 → CSV 생성
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

HEADERS = {"User-Agent": "Mozilla/5.0"}
MODEL_NAME = "snunlp/KR-FinBert-SC"
BATCH_SIZE = 32
MAX_LEN = 512

TODAY = dt.date.today().strftime("%Y-%m-%d")
TODAY_DOT = dt.date.today().strftime("%Y.%m.%d")
TODAY_COMPACT = dt.date.today().strftime("%Y%m%d")

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

###############################################################
# 2️⃣ 종목코드 로드
###############################################################

def norm_name(x):
    x=str(x)
    x=re.sub(r"\s+","",x)
    x=re.sub(r"[()·\-\.\,]","",x)
    return x

fund = pd.read_csv("fundamental_2025_Q1.csv", dtype=str)
name_col=[c for c in fund.columns if "종목" in c and "명" in c][0]
code_col=[c for c in fund.columns if "코드" in c][0]

fund[code_col]=fund[code_col].str.zfill(6)
fund["norm"]=fund[name_col].apply(norm_name)
mapping=dict(zip(fund["norm"],fund[code_col]))
companies=fund[name_col].tolist()

###############################################################
# 3️⃣ 동아일보
###############################################################

def crawl_donga(company, idx, total):
    rows=[]
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
            rows.append([company,TODAY,text])

        log(f"[{idx}/{total}] {company} - 동아일보 완료 ({len(rows)}건)")
    except Exception as e:
        log(f"[{idx}/{total}] {company} - 동아일보 실패")

    return rows

###############################################################
# 4️⃣ 조선일보
###############################################################

def crawl_chosun(company, idx, total):
    rows=[]
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
            rows.append([company,TODAY,text])

        log(f"[{idx}/{total}] {company} - 조선일보 완료 ({len(rows)}건)")
    except:
        log(f"[{idx}/{total}] {company} - 조선일보 실패")

    return rows

###############################################################
# 5️⃣ 한국경제
###############################################################

def crawl_hankyung(company, idx, total):
    rows=[]
    try:
        url=f"https://search.hankyung.com/search/news?query={company}&sort=DATE/DESC&period=DATE&sdate={TODAY_DOT}&edate={TODAY_DOT}"
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
            rows.append([company,TODAY,text])

        log(f"[{idx}/{total}] {company} - 한국경제 완료 ({len(rows)}건)")
    except:
        log(f"[{idx}/{total}] {company} - 한국경제 실패")

    return rows

###############################################################
# 6️⃣ 크롤링 실행
###############################################################

all_rows=[]
seen=set()
total=len(companies)

with ThreadPoolExecutor(max_workers=8) as ex:
    futures=[]
    for idx,c in enumerate(companies,1):
        futures.append(ex.submit(crawl_donga,c,idx,total))
        futures.append(ex.submit(crawl_chosun,c,idx,total))
        futures.append(ex.submit(crawl_hankyung,c,idx,total))

    for f in as_completed(futures):
        for row in f.result():
            h=make_hash(row[0],row[1],row[2])
            if h in seen: continue
            seen.add(h)
            all_rows.append(row)

df=pd.DataFrame(all_rows,columns=["company","date","text"])
print("총 수집 기사수:",len(df))

###############################################################
# 7️⃣ FinBERT
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

df=score_news(df)

###############################################################
# 8️⃣ 종목코드 매칭
###############################################################

df["norm"]=df["company"].apply(norm_name)
df["종목코드"]=df["norm"].map(mapping)
df=df.dropna(subset=["종목코드"])

###############################################################
# 9️⃣ 기업-날짜 평균 → CSV
###############################################################

final=df.groupby(["company","종목코드","date"])["score"].mean().reset_index()
final.columns=["기업명","종목코드","날짜","점수"]

outfile=f"news_score_{TODAY_COMPACT}.csv"
final.to_csv(outfile,index=False,encoding="utf-8-sig")

print("완료:",outfile)
