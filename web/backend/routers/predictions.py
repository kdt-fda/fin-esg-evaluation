from fastapi import APIRouter, HTTPException, Query
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


def _calc_short_confidence(da, mape) -> float:
    da_val = _safe_float(da) or 0.0
    mape_val = _safe_float(mape) or 0.0

    score = (da_val * 0.6) + (max(0.0, 100.0 - mape_val) * 0.4)
    return round(score, 2)


def _calc_long_confidence(hr, ic, da) -> float:
    hr_val = _safe_float(hr) or 0.0
    ic_val = _safe_float(ic) or 0.0
    da_val = _safe_float(da) or 0.0

    score = (hr_val * 0.4) + (ic_val * 0.35) + (da_val * 0.25)
    return round(score, 2)


# -----------------------------
# SHORT TERM
# 실제 종가(STOCK_TB.close)는 /stocks/{code}/prices 에서 별도 조회
# 여기서는 단기 예측(SHORT_PRED_TB) + 설명(SHORT_LLM_TB) + confidence 반환
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
                    p.trade_date      AS trade_date,
                    p.prediction      AS predicted_value,
                    p.shap_feature    AS shap_feature,
                    p.shap_value      AS shap_value,
                    p.DA              AS da,
                    p.MAPE            AS mape,
                    l.interpretation  AS interpretation
                FROM SHORT_PRED_TB p
                LEFT JOIN SHORT_LLM_TB l
                    ON p.trade_date = l.trade_date
                   AND p.ticker = l.ticker
                WHERE p.ticker = %s
                  AND p.trade_date >= CURDATE()
                ORDER BY p.trade_date ASC
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
                    "date": _to_ymd(r["trade_date"]),
                    "predicted": _safe_float(r["predicted_value"]),
                }

                if r["shap_feature"] is not None and r["shap_value"] is not None:
                    point["reason"] = [
                        {
                            "factor": str(r["shap_feature"]),
                            "impact": r["interpretation"] or "",
                            "contribution": _safe_float(r["shap_value"]),
                        }
                    ]

                if r["interpretation"]:
                    point["changeReason"] = r["interpretation"]

                data.append(point)

            # 같은 배치의 예측이면 DA/MAPE가 동일하거나 매우 유사하다고 보고 첫 row 기준 사용
            confidence = _calc_short_confidence(
                rows[0].get("da"),
                rows[0].get("mape"),
            )

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
# confidence는 선택 종목의 최신 DA/HR/IC 기준으로 계산
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
                        p1.trade_date
                    FROM LONG_PRED_TB p1
                    INNER JOIN (
                        SELECT
                            ticker,
                            MAX(trade_date) AS max_trade_date
                        FROM LONG_PRED_TB
                        GROUP BY ticker
                    ) latest
                        ON p1.ticker = latest.ticker
                       AND p1.trade_date = latest.max_trade_date
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

            # 선택 종목의 최신 confidence용 지표 조회
            confidence_sql = """
                SELECT
                    p.DA AS da,
                    p.HR AS hr,
                    p.IC AS ic
                FROM LONG_PRED_TB p
                WHERE p.ticker = %s
                ORDER BY p.trade_date DESC
                LIMIT 1
            """
            cur.execute(confidence_sql, [code])
            confidence_row = cur.fetchone()

            if confidence_row:
                confidence = _calc_long_confidence(
                    confidence_row.get("hr"),
                    confidence_row.get("ic"),
                    confidence_row.get("da"),
                )
            else:
                confidence = 0

            return {
                "confidence": confidence,
                "data": data,
            }

    finally:
        conn.close()