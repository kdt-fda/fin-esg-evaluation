from __future__ import annotations

import os
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

LOOKBACK_FETCH = 40
LOOKBACK_TURNING = 20
MAX_TURNING_POINTS = 5


def get_db_engine():
    required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    values = {k: os.environ.get(k) for k in required}

    if not all(values.values()):
        raise ValueError("DB 환경변수가 설정되지 않았습니다.")

    return create_engine(
        f"mysql+pymysql://{values['DB_USER']}:{values['DB_PASSWORD']}"
        f"@{values['DB_HOST']}:{values['DB_PORT']}/{values['DB_NAME']}"
    )


def load_turning_data(ticker: str, lookback_days: int = LOOKBACK_FETCH) -> pd.DataFrame:
    sql = text("""
        SELECT
            trade_date,
            ticker,
            stock_name,
            golden_cross_5_20,
            death_cross_5_20,
            bb_breakout,
            msci_event,
            macd,
            macd_signal
        FROM STOCK_TB
        WHERE ticker = :ticker
        ORDER BY trade_date DESC
        LIMIT :limit_n
    """)

    engine = get_db_engine()
    try:
        df = pd.read_sql(sql, engine, params={"ticker": ticker, "limit_n": lookback_days})
    finally:
        engine.dispose()

    if df.empty:
        return df

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.sort_values("trade_date").reset_index(drop=True)


def _to_int(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _to_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _date_str(value) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def build_turning_points_from_df(
    df: pd.DataFrame,
    turning_lookback: int = LOOKBACK_TURNING,
) -> dict:
    if df.empty:
        return {
            "stock_name": "",
            "ticker": "",
            "as_of_date": None,
            "turning_points": [],
        }

    recent = df.tail(turning_lookback).copy()
    latest = recent.iloc[-1]

    turning_points = []

    for _, row in recent.iterrows():
        date = _date_str(row["trade_date"])

        if _to_int(row.get("golden_cross_5_20")) == 1:
            turning_points.append({
                "date": date,
                "type": "golden_cross",
                "title": "골든크로스 발생",
                "strength": "high",
                "summary": "5일선이 20일선을 상향 돌파하며 단기 추세 개선 신호가 나타났습니다.",
            })

        if _to_int(row.get("death_cross_5_20")) == 1:
            turning_points.append({
                "date": date,
                "type": "death_cross",
                "title": "데드크로스 발생",
                "strength": "high",
                "summary": "5일선이 20일선을 하향 이탈하며 단기 조정 압력이 커졌습니다.",
            })

        if _to_int(row.get("bb_breakout")) == 1:
            turning_points.append({
                "date": date,
                "type": "bb_upper_breakout",
                "title": "볼린저 상단 돌파",
                "strength": "high",
                "summary": "상단 밴드 돌파가 나타나며 단기 강세와 변동성 확대 가능성이 함께 부각됐습니다.",
            })

        if _to_int(row.get("bb_breakout")) == -1:
            turning_points.append({
                "date": date,
                "type": "bb_lower_breakout",
                "title": "볼린저 하단 이탈",
                "strength": "high",
                "summary": "하단 밴드 이탈이 나타나 단기 약세 압력이 강화됐을 가능성이 있습니다.",
            })

        if _to_int(row.get("msci_event")) == 1:
            turning_points.append({
                "date": date,
                "type": "msci_event",
                "title": "MSCI 이벤트 구간",
                "strength": "medium",
                "summary": "리밸런싱 이슈로 인해 단기 수급 변동성이 확대될 수 있는 시점입니다.",
            })

    for i in range(1, len(recent)):
        prev_row = recent.iloc[i - 1]
        curr_row = recent.iloc[i]

        prev_macd = _to_float(prev_row.get("macd"))
        prev_signal = _to_float(prev_row.get("macd_signal"))
        curr_macd = _to_float(curr_row.get("macd"))
        curr_signal = _to_float(curr_row.get("macd_signal"))

        if None in (prev_macd, prev_signal, curr_macd, curr_signal):
            continue

        date = _date_str(curr_row["trade_date"])

        if prev_macd <= prev_signal and curr_macd > curr_signal:
            turning_points.append({
                "date": date,
                "type": "macd_cross_up",
                "title": "MACD 매수 신호",
                "strength": "medium",
                "summary": "MACD가 시그널선을 상향 돌파하며 단기 반등 또는 상승 탄력 강화 가능성을 시사했습니다.",
            })

        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            turning_points.append({
                "date": date,
                "type": "macd_cross_down",
                "title": "MACD 약세 전환",
                "strength": "medium",
                "summary": "MACD가 시그널선을 하향 이탈하며 단기 모멘텀 둔화 가능성이 부각됐습니다.",
            })

    turning_points.sort(key=lambda x: x["date"])

    deduped = []
    seen = set()
    for point in turning_points:
        key = (point["date"], point["type"])
        if key not in seen:
            deduped.append(point)
            seen.add(key)

    return {
        "stock_name": str(latest.get("stock_name") or ""),
        "ticker": str(latest.get("ticker") or ""),
        "as_of_date": _date_str(latest["trade_date"]),
        "turning_points": deduped[-MAX_TURNING_POINTS:],
    }


def build_turning_points(ticker: str, turning_lookback: int = LOOKBACK_TURNING) -> dict:
    df = load_turning_data(ticker)
    return build_turning_points_from_df(df, turning_lookback=turning_lookback)