from fastapi import APIRouter, HTTPException, Query
import json
import pandas as pd

from db.database import get_connection

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


# -----------------------------
# SHORT TERM
# 실제 종가(STOCK_TB.close)는 /stocks/{code}/prices 에서 별도 조회
# 여기서는 단기 예측(SHORT_PRED_TB) + 설명(SHORT_LLM_TB) + confidence 반환
# confidence는 DB의 conf_score 사용
# -----------------------------
@router.get("/short")
def predict_short(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    p.pred_date       AS pred_date,
                    p.prediction      AS predicted_value,
                    p.shap_feature    AS shap_feature,
                    p.shap_value      AS shap_value,
                    p.conf_score      AS conf_score,
                    l.interpretation  AS interpretation
                FROM SHORT_PRED_TB p
                LEFT JOIN SHORT_LLM_TB l
                    ON p.pred_date = l.pred_date
                   AND p.ticker = l.ticker
                WHERE p.ticker = %s
                  AND p.pred_date >= CURDATE()
                ORDER BY p.pred_date ASC
                LIMIT 20
            """

            cur.execute(sql, [code])
            rows = cur.fetchall()

            if not rows:
                return {
                    "confidence": 0,
                    "pastCount": 0,
                    "data": [],
                }

            data = []

            for r in rows:
                point = {
                    "date": _to_ymd(r["pred_date"]),
                    "predicted": _safe_json(r["predicted_value"]),
                }

                shap_feature = _safe_json(r["shap_feature"])
                shap_value = _safe_json(r["shap_value"])

                if shap_feature is not None or shap_value is not None:
                    # shap_feature/shap_value가 JSON 배열일 수도 있고 단일값일 수도 있으니 유연하게 처리
                    if isinstance(shap_feature, list) and isinstance(shap_value, list):
                        reason = []
                        for feature, contribution in zip(shap_feature, shap_value):
                            reason.append({
                                "factor": str(feature),
                                "impact": r["interpretation"] or "",
                                "contribution": _safe_float(contribution),
                            })
                        point["reason"] = reason
                    else:
                        point["reason"] = [
                            {
                                "factor": str(shap_feature) if shap_feature is not None else "",
                                "impact": r["interpretation"] or "",
                                "contribution": _safe_float(shap_value),
                            }
                        ]

                if r["interpretation"]:
                    point["changeReason"] = r["interpretation"]

                data.append(point)

            confidence = _safe_float(rows[0].get("conf_score")) or 0

            return {
                "confidence": confidence,
                "pastCount": 0,
                "data": data,
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

            # 같은 섹터 전체 종목 + 최신 score 조회
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
                LEFT JOIN (
                    SELECT
                        p1.ticker,
                        p1.score,
                        p1.pred_date
                    FROM LONG_PRED_TB p1
                    INNER JOIN (
                        SELECT
                            ticker,
                            MAX(pred_date) AS max_pred_date
                        FROM LONG_PRED_TB
                        GROUP BY ticker
                    ) latest
                        ON p1.ticker = latest.ticker
                       AND p1.pred_date = latest.max_pred_date
                ) lp
                    ON k.ticker = lp.ticker
                WHERE k.sector_code = %s
                  AND k.is_active = TRUE
                ORDER BY lp.score DESC, k.stock_name ASC
            """
            cur.execute(ranking_sql, [sector_code])
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