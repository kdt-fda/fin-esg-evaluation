
from fastapi import APIRouter, HTTPException, Query
from datetime import timedelta
import os
import pymysql
import pandas as pd
import numpy as np

from services.data_joiner import StockDataJoiner  # TODO: 실제 경로에 맞게 수정 (예: from app.services...)


router = APIRouter(prefix="/predictions", tags=["predictions"])
joiner = StockDataJoiner()


def _connect():
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME", "STOCK_DB")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _get_stock_name_by_ticker(ticker: str) -> str | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT stock_name
                FROM KOSPI200_STOCKS_TB
                WHERE ticker = %s
                LIMIT 1
                """,
                (ticker,),
            )
            row = cur.fetchone()
            return row["stock_name"] if row else None
    finally:
        conn.close()


# =========================
# Chart formatting helpers
# React ChartDataPoint.date가 "M/D" 형태로 쓰이도록 맞춤
# =========================
def _to_mmdd(d: pd.Timestamp) -> str:
    return f"{int(d.month)}/{int(d.day)}"


def _to_month_label(d: pd.Timestamp) -> str:
    return f"{int(d.month)}월"


# =========================
# TODO: 나중에 XGBoost 붙일 때 교체될 부분들
# - 여기서는 "예측값(preds)"이 없을 때도 UI가 돌게 더미 예측을 만들어줌
# - 모델 연결하면:
#   1) preds_short / preds_long을 만들어서 아래 builder에 주입
#   2) reason/changeReason는 SHAP/규칙 기반 등으로 실제 근거로 교체
# =========================
def _dummy_future_prices_by_randomwalk(
    base_price: float,
    steps: int,
    vol: float,
    drift: float = 0.001,
) -> list[float]:
    """TODO: (모델 연결 후 제거/대체) 랜덤워크로 더미 예측 생성"""
    current = base_price
    out = []
    for _ in range(steps):
        shock = float(np.random.normal(0.0, vol))
        change = drift + shock
        current = float(round(current * (1 + change)))
        out.append(current)
    return out


def _dummy_reasons(change: float) -> tuple[list[dict], str]:
    """TODO: (모델 연결 후 제거/대체) 더미 reason/changeReason 생성"""
    up = change >= 0
    if up:
        return (
            [
                {"factor": "모멘텀", "impact": "최근 단기 흐름 양호(더미)", "contribution": 1.0},
                {"factor": "수급", "impact": "수급 개선 가정(더미)", "contribution": 0.5},
            ],
            "단기 더미 예측(모델 연결 전)",
        )
    return (
        [
            {"factor": "변동성", "impact": "단기 변동성 확대(더미)", "contribution": -0.8},
            {"factor": "시장", "impact": "시장 조정 가정(더미)", "contribution": -0.5},
        ],
        "단기 더미 예측(모델 연결 전)",
    )


# =========================
# Builders: df -> ChartDataPoint[]
# - 실제 차트는 이 변환이 꼭 필요함
# - TODO 표시된 부분만 나중에 모델 예측값/근거로 교체하면 됨
# =========================
def build_short_chart_points(
    df: pd.DataFrame,
    horizon_days: int,
    preds: list[float] | None = None,
    include_reasons: bool = True,
) -> list[dict]:
    """
    단기 차트용 데이터 생성.
    - 과거 7개: actual
    - 오늘(마지막 row): actual + predicted(기준값)
    - 미래 horizon_days: predicted (+ optional reason)

    preds:
      - TODO: XGBoost 단기 모델 예측 결과를 [horizon_days] 길이로 넣어주면 더미 생성이 필요 없음
    """
    df = df.sort_values("trade_date").copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    if df.empty or "close" not in df.columns:
        return []

    # 과거 7 + 오늘
    tail = df.tail(8)
    base_close = float(tail.iloc[-1]["close"])
    base_date = pd.to_datetime(tail.iloc[-1]["trade_date"])

    out: list[dict] = []

    # 과거 actual
    for i in range(len(tail) - 1):
        row = tail.iloc[i]
        out.append({"date": _to_mmdd(row["trade_date"]), "actual": float(row["close"])})

    # 오늘 actual+predicted(기준)
    out.append({"date": _to_mmdd(base_date), "actual": base_close, "predicted": base_close})

    # 미래 predicted 생성
    if preds is None:
        # TODO: 모델 연결 후 제거/대체 (preds를 모델에서 만들어서 주입)
        recent = df.tail(30).copy()
        recent["ret"] = recent["close"].pct_change()
        vol = float(np.nan_to_num(recent["ret"].std(), nan=0.01))
        vol = max(0.005, min(vol, 0.05))
        preds = _dummy_future_prices_by_randomwalk(base_close, horizon_days, vol=vol, drift=0.001)

    # predicted 포인트 생성
    current_for_change = base_close
    for k in range(1, horizon_days + 1):
        future_date = base_date + timedelta(days=k)

        predicted_price = float(preds[k - 1])
        point = {
            "date": _to_mmdd(future_date),
            "predicted": predicted_price,
        }

        if include_reasons:
            # TODO: 모델 연결 후 "실제 근거"로 교체 (SHAP/룰 기반 등)
            change = (predicted_price / current_for_change) - 1 if current_for_change else 0.0
            reasons, change_reason = _dummy_reasons(change)
            point["reason"] = reasons
            point["changeReason"] = change_reason

        out.append(point)
        current_for_change = predicted_price

    return out


def build_long_chart_points(
    df: pd.DataFrame,
    horizon_months: int,
    preds: list[float] | None = None,
    include_reasons: bool = True,
) -> list[dict]:
    """
    장기 차트용 데이터 생성.
    - 월말 종가로 리샘플 후:
      과거 6개월 actual
      현재(기준월) actual+predicted
      미래 horizon_months predicted (+ optional reason)

    preds:
      - TODO: XGBoost 장기 모델 예측 결과를 [horizon_months] 길이로 넣어주면 더미 생성 불필요
    """
    df = df.sort_values("trade_date").copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    if df.empty or "close" not in df.columns:
        return []

    close_series = df.set_index("trade_date")["close"].astype(float)
    try:
        s = close_series.resample("ME").last().dropna()  
    except ValueError:
        s = close_series.resample("M").last().dropna()
    
    if s.empty:
        return []

    tail = s.tail(7)  # 과거 6개월 + 현재
    base_close = float(tail.iloc[-1])
    base_date = tail.index[-1]

    out: list[dict] = []

    # 과거 actual
    for i in range(len(tail) - 1):
        d = tail.index[i]
        out.append({"date": _to_month_label(d), "actual": float(tail.iloc[i])})

    # 현재
    out.append({"date": _to_month_label(base_date), "actual": base_close, "predicted": base_close})

    # 미래 predicted
    if preds is None:
        # TODO: 모델 연결 후 제거/대체
        current = base_close
        preds = []
        for _ in range(horizon_months):
            growth = 0.02 + float(np.random.uniform(0.0, 0.02))  # 더미 성장률
            current = float(round(current * (1 + growth)))
            preds.append(current)

    current_for_change = base_close
    for k in range(1, horizon_months + 1):
        future = base_date + pd.DateOffset(months=k)
        predicted_price = float(preds[k - 1])

        point = {
            "date": _to_month_label(future),
            "predicted": predicted_price,
        }

        if include_reasons:
            # TODO: 모델 연결 후 실제 근거로 교체
            point["reason"] = [
                {"factor": "실적", "impact": "실적 개선 가정(더미)", "contribution": 2.0},
                {"factor": "거시", "impact": "거시 안정 가정(더미)", "contribution": 1.0},
            ]
            point["changeReason"] = "중장기 더미 예측(모델 연결 전)"

        out.append(point)
        current_for_change = predicted_price

    return out


# =========================
# Endpoints
# - 프론트가 바로 쓰기 좋은 형태:
#   { confidence: number, data: ChartDataPoint[] }
# =========================
@router.get("/short")
def predict_short(
    code: str = Query(..., description="ticker 예: 005930"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    horizon_days: int = Query(7, ge=1, le=30),
):
    stock_name = _get_stock_name_by_ticker(code)
    if not stock_name:
        raise HTTPException(status_code=404, detail="해당 ticker의 종목을 찾을 수 없습니다.")

    df = joiner.load_full_features(stock_name, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="DB에서 데이터를 찾을 수 없습니다.")

    # TODO: 여기서 단기 XGBoost 모델을 로드/호출해서 preds를 만들 것
    # 예: preds_short = predictor.predict_short(df, horizon_days)
    preds_short = None  # 모델 연결 전에는 None -> 더미 생성

    data = build_short_chart_points(
        df=df,
        horizon_days=horizon_days,
        preds=preds_short,            # TODO: 모델 예측값으로 교체
        include_reasons=True,         # TODO: SHAP 등 실제 근거 준비되면 True 유지, 아니면 False도 가능
    )

    # TODO: confidence를 모델의 성능/불확실성 기반으로 계산하거나 DB에 저장된 값을 내려주기
    return {"confidence": 85, "data": data}


@router.get("/long")
def predict_long(
    code: str = Query(..., description="ticker 예: 005930"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    horizon_months: int = Query(6, ge=1, le=24),
):
    stock_name = _get_stock_name_by_ticker(code)
    if not stock_name:
        raise HTTPException(status_code=404, detail="해당 ticker의 종목을 찾을 수 없습니다.")

    df = joiner.load_full_features(stock_name, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="DB에서 데이터를 찾을 수 없습니다.")

    # TODO: 여기서 장기 XGBoost 모델을 로드/호출해서 preds를 만들 것
    # 예: preds_long = predictor.predict_long(df, horizon_months)
    preds_long = None  # 모델 연결 전에는 None -> 더미 생성

    data = build_long_chart_points(
        df=df,
        horizon_months=horizon_months,
        preds=preds_long,            # TODO: 모델 예측값으로 교체
        include_reasons=True,        # TODO: 실제 근거 준비되면 True 유지
    )

    # TODO: confidence 산출 로직 추가
    return {"confidence": 78, "data": data}