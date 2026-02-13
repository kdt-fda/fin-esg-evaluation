import io
import csv
import sys
import math
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# =========================
# 설정
# =========================
INFILE  = "news.csv"
OUTFILE = "news_score.csv"

MODEL_NAME = "snunlp/KR-FinBert-SC"
COMP_COL   = "company"
DATE_COL   = "date"
TEXT_COL   = "full_text"

BATCH_SIZE = 32
MAX_LEN    = 256

# =========================
# CSV 파서 field limit 확장
# =========================
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(10**9)

# =========================
# 로드
# =========================
def load_news_csv(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "cp949"]:
        try:
            with open(path, "rb") as f:
                wrapper = io.TextIOWrapper(f, encoding=enc, errors="replace", newline="")
                df = pd.read_csv(
                    wrapper,
                    engine="python",
                    on_bad_lines="skip"
                )
            print(f"✅ loaded with encoding={enc} | rows={len(df)}")
            return df
        except Exception as e:
            print(f"⚠ load failed encoding={enc} -> {str(e)[:120]}")
    raise RuntimeError("news.csv 로드 실패")

# =========================
# 디바이스
# =========================
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
use_fp16 = (device.type == "cuda")
print("device:", device, "| fp16:", use_fp16)

# =========================
# 모델 로드
# =========================
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.to(device)
model.eval()

num_labels = int(model.config.num_labels)
label_values = torch.linspace(-1.0, 1.0, steps=num_labels, device=device)
print("num_labels:", num_labels, "| label_values:", label_values.detach().cpu().numpy())

# =========================
# 배치 점수 함수
# =========================
@torch.no_grad()
def score_batch(texts):
    enc = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_LEN,
        return_tensors="pt"
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    if use_fp16:
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            logits = model(**enc).logits
    else:
        logits = model(**enc).logits

    probs = torch.softmax(logits, dim=-1)
    scores = (probs * label_values).sum(dim=-1)
    return scores.detach().float().cpu().numpy()

# =========================
# 데이터 로드/정리
# =========================
df = load_news_csv(INFILE)

need = {COMP_COL, DATE_COL, TEXT_COL}
missing = need - set(df.columns)
if missing:
    raise RuntimeError(f"필수 컬럼 없음: {missing} / 현재 컬럼: {list(df.columns)}")

df[COMP_COL] = df[COMP_COL].astype(str).str.strip()
df[TEXT_COL] = df[TEXT_COL].astype(str).fillna("").str.strip()

df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
df = df[df[DATE_COL].notna()].copy()
df = df[df[TEXT_COL].str.len() > 0].copy()

# =========================
# 기사 단위 점수 계산
# =========================
texts = df[TEXT_COL].tolist()
n = len(texts)

scores = np.empty(n, dtype=np.float32)
steps = math.ceil(n / BATCH_SIZE)

for i in range(steps):
    s = i * BATCH_SIZE
    e = min((i + 1) * BATCH_SIZE, n)
    scores[s:e] = score_batch(texts[s:e])

    if (i + 1) % 50 == 0 or (i + 1) == steps:
        print(f"progress: {e}/{n} ({(e/n)*100:.1f}%)")

df["score"] = scores

# =========================
# (company, date)별 평균
# =========================
df["date_only"] = df[DATE_COL].dt.strftime("%Y-%m-%d")

out = (
    df.groupby([COMP_COL, "date_only"], as_index=False)["score"]
      .mean()
      .rename(columns={"date_only": "date"})
)

# 정렬: 기업 오름차순, 날짜 내림차순
out = out.sort_values(["company", "date"], ascending=[True, False]).reset_index(drop=True)

# 저장
out.to_csv(OUTFILE, index=False, encoding="utf-8-sig")

