from fastapi import APIRouter, HTTPException, Query
import json
import pandas as pd

from db.database import get_connection
from services.feature_context import build_feature_contexts

router = APIRouter(prefix="/predictions", tags=["predictions"])


# -----------------------------
# 공통 헬퍼
# -----------------------------
def _to_ymd(value) -> str:
    if value is None:
        return ""
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _to_month_label(value) -> str:
    if value is None:
        return ""
    d = pd.to_datetime(value)
    return f"{int(d.month)}월"


def _safe_float(value):
    if value is None:
        return None
    return float(value)


def _safe_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_return_list(value):
    """
    SHORT_PRED_TB.prediction JSON 문자열에서
    D+1 ~ D+20 예측 수익률(%) 리스트를 추출
    예:
    '[-0.99, -1.14, ...]' -> [-0.99, -1.14, ...]
    """
    parsed = _safe_json(value)

    if parsed is None:
        return []

    if isinstance(parsed, list):
        result = []
        for v in parsed:
            fv = _safe_float(v)
            if fv is not None:
                result.append(fv)
        return result

    return []


# -----------------------------
# SHORT TERM
# 실제 종가(STOCK_TB.close)는 /stocks/{code}/prices 에서 별도 조회
# 여기서는 단기 예측(SHORT_PRED_TB) + confidence 반환
# confidence는 DB의 conf_score 사용
# -----------------------------
@router.get("/short")
def predict_short(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 가장 최근 종가 조회
            latest_price_sql = """
                SELECT
                    trade_date,
                    close
                FROM STOCK_TB
                WHERE ticker = %s
                ORDER BY trade_date DESC
                LIMIT 1
            """
            cur.execute(latest_price_sql, [code])
            latest_price_row = cur.fetchone()

            if not latest_price_row or latest_price_row.get("close") is None:
                return {
                    "confidence": 0,
                    "pastCount": 0,
                    "data": [],
                }

            latest_close = _safe_float(latest_price_row["close"])

            # 최신 단기 예측 배치 1건 조회
            sql = """
                SELECT
                    p.pred_date       AS pred_date,
                    p.prediction      AS predicted_value,
                    p.conf_score      AS conf_score
                FROM SHORT_PRED_TB p
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """

            cur.execute(sql, [code])
            row = cur.fetchone()

            if not row:
                return {
                    "confidence": 0,
                    "pastCount": 0,
                    "data": [],
                }

            return_list = _extract_return_list(row["predicted_value"])

            if not return_list:
                return {
                    "confidence": _safe_float(row.get("conf_score")) or 0,
                    "pastCount": 0,
                    "data": [],
                }

            base_date = pd.to_datetime(row["pred_date"])
            data = []

            for i, predicted_return in enumerate(return_list, start=1):
                predicted_price = latest_close * (1 + (predicted_return / 100.0))
                target_date = base_date + pd.offsets.BDay(i)

                point = {
                    "date": target_date.strftime("%Y-%m-%d"),
                    "predicted": round(predicted_price, 2),
                }

                data.append(point)

            confidence = _safe_float(row.get("conf_score")) or 0

            return {
                "confidence": confidence,
                "pastCount": 0,
                "data": data,
            }

    finally:
        conn.close()


# -----------------------------
# SHORT TERM INTERPRETATION
# SHORT_LLM_TB.interpretation(JSON) 반환
# DB에 데이터가 없으면 빈 구조 반환
# interpretation 자체가 short 전용 JSON이라고 가정
# -----------------------------
@router.get("/short/interpretation")
def get_short_interpretation(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM SHORT_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(sql, [code])
            row = cur.fetchone()

            if not row:
                return {
                    "ticker": code,
                    "pred_date": None,
                    "interpretation": None,
                    "feature_contexts": {},
                }

            interpretation = _safe_json(row["interpretation"])
            feature_contexts = build_feature_contexts(cur, code, interpretation)

            return {
                "ticker": code,
                "pred_date": _to_ymd(row["pred_date"]),
                "interpretation": interpretation,
                "feature_contexts": feature_contexts,
            }
    finally:
        conn.close()


# -----------------------------
# LONG TERM
# 선택 종목의 섹터를 찾고,
# 같은 섹터에 속한 모든 종목의 LONG_PRED_TB.score 반환
# confidence는 선택 종목의 최신 conf_score 사용
# -----------------------------
@router.get("/long")
def predict_long(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 선택 종목의 sector_code 조회
            stock_sql = """
                SELECT
                    k.ticker,
                    k.stock_name,
                    k.sector_code,
                    s.sector_name
                FROM KOSPI200_STOCKS_TB k
                LEFT JOIN SECTOR_TB s
                    ON k.sector_code = s.sector_code
                WHERE k.ticker = %s
                LIMIT 1
            """
            cur.execute(stock_sql, [code])
            selected_stock = cur.fetchone()

            if not selected_stock:
                raise HTTPException(status_code=404, detail="선택한 종목을 찾을 수 없습니다.")

            sector_code = selected_stock.get("sector_code")
            sector_name = selected_stock.get("sector_name")

            if not sector_code:
                return {
                    "confidence": 0,
                    "data": [],
                }

            # 선택 종목의 최신 pred_date를 기준으로 같은 시점의 섹터 랭킹만 조회
            latest_pred_sql = """
                SELECT MAX(pred_date) AS latest_pred_date
                FROM LONG_PRED_TB
                WHERE ticker = %s
            """
            cur.execute(latest_pred_sql, [code])
            latest_pred_row = cur.fetchone()
            latest_pred_date = latest_pred_row.get("latest_pred_date") if latest_pred_row else None

            if not latest_pred_date:
                return {
                    "confidence": 0,
                    "data": [],
                }

            # 같은 섹터 전체 종목 + 동일 시점 score 조회
            ranking_sql = """
                SELECT
                    k.ticker AS code,
                    k.stock_name AS name,
                    k.sector_code AS sector_code,
                    s.sector_name AS sector,
                    lp.score AS score
                FROM KOSPI200_STOCKS_TB k
                LEFT JOIN SECTOR_TB s
                    ON k.sector_code = s.sector_code
                LEFT JOIN LONG_PRED_TB lp
                    ON k.ticker = lp.ticker
                   AND lp.pred_date = %s
                WHERE k.sector_code = %s
                  AND k.is_active = TRUE
                ORDER BY lp.score DESC, k.stock_name ASC
            """
            cur.execute(ranking_sql, [latest_pred_date, sector_code])
            rows = cur.fetchall()

            data = []
            for r in rows:
                if r.get("score") is None:
                    continue

                data.append({
                    "code": r["code"],
                    "name": r["name"],
                    "sector": r["sector"] or sector_name or "",
                    "score": _safe_float(r["score"]),
                })

            # 선택 종목의 최신 conf_score 조회
            confidence_sql = """
                SELECT
                    p.conf_score AS conf_score
                FROM LONG_PRED_TB p
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """
            cur.execute(confidence_sql, [code])
            confidence_row = cur.fetchone()

            confidence = _safe_float(confidence_row.get("conf_score")) if confidence_row else 0
            if confidence is None:
                confidence = 0

            return {
                "confidence": confidence,
                "data": data,
            }

    finally:
        conn.close()


# -----------------------------
# LONG TERM INTERPRETATION
# LONG_LLM_TB.interpretation(JSON) 반환
# DB에 데이터가 없으면 빈 구조 반환
# interpretation 자체가 long 전용 JSON이라고 가정
# -----------------------------
@router.get("/long/interpretation")
def get_long_interpretation(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM LONG_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(sql, [code])
            row = cur.fetchone()

            if not row:
                return {
                    "ticker": code,
                    "pred_date": None,
                    "interpretation": None,
                    "feature_contexts": {},
                }

            interpretation = _safe_json(row["interpretation"])
            feature_contexts = build_feature_contexts(cur, code, interpretation)

            return {
                "ticker": code,
                "pred_date": _to_ymd(row["pred_date"]),
                "interpretation": interpretation,
                "feature_contexts": feature_contexts,
            }
    finally:
        conn.close()