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


# -----------------------------
# SHORT TERM
# 실제 종가(STOCK_TB.close) + 단기 예측(SHORT_PRED_TB) + 설명(SHORT_LLM_TB)
# -----------------------------
@router.get("/short")
def predict_short(
    code: str = Query(..., description="ticker 예: 005930"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=1000, description="최근 N건만 조회"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    s.trade_date                      AS trade_date,
                    s.close                           AS actual_close,
                    p.prediction                      AS predicted_value,
                    p.shap_feature                    AS shap_feature,
                    p.shap_value                      AS shap_value,
                    l.interpretation                  AS interpretation
                FROM STOCK_TB s
                LEFT JOIN SHORT_PRED_TB p
                    ON s.trade_date = p.trade_date
                   AND s.ticker = p.ticker
                LEFT JOIN SHORT_LLM_TB l
                    ON s.trade_date = l.trade_date
                   AND s.ticker = l.ticker
                WHERE s.ticker = %s
            """
            params = [code]

            if start_date:
                sql += " AND s.trade_date >= %s"
                params.append(start_date)

            if end_date:
                sql += " AND s.trade_date <= %s"
                params.append(end_date)

            sql += " ORDER BY s.trade_date ASC"

            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()

            if not rows:
                raise HTTPException(status_code=404, detail="단기 예측 데이터를 찾을 수 없습니다.")

            data = []
            past_count = 0

            for r in rows:
                point = {
                    "date": _to_ymd(r["trade_date"]),
                    "actual": _safe_float(r["actual_close"]),
                }

                # prediction이 단일값일 경우
                if r["predicted_value"] is not None:
                    point["predicted"] = _safe_float(r["predicted_value"])

                # shap_feature / shap_value / interpretation 이 있으면 reason 구성
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

                # predicted가 아직 없는 구간은 과거(actual) 구간으로 간주
                if r["predicted_value"] is None:
                    past_count += 1

                # -----------------------------------------
                # [배열(JSON)로 바뀌는 경우 예시]
                #
                # prediction 컬럼이 예:
                # [72000, 72100, 72300]
                # 같은 JSON 배열이면, 위의 단일값 처리 대신
                # "현재 row 하나"가 아니라 "미래 여러 포인트"를 펼쳐야 합니다.
                #
                # 예시:
                #
                # import json
                # preds = r["predicted_value"]
                # if isinstance(preds, str):
                #     preds = json.loads(preds)
                #
                # for idx, pred in enumerate(preds, start=1):
                #     future_date = pd.to_datetime(r["trade_date"]) + pd.Timedelta(days=idx)
                #     data.append({
                #         "date": _to_ymd(future_date),
                #         "predicted": float(pred)
                #     })
                #
                # 이 경우 현재 SQL / 로직 구조를 조금 바꾸는 게 더 깔끔합니다.
                # -----------------------------------------

            return {
                "confidence": 0,   # 나중에 별도 컬럼/테이블 생기면 교체
                "pastCount": past_count,
                "data": data,
            }

    finally:
        conn.close()


# -----------------------------
# LONG TERM
# 실제 월말 종가(STOCK_TB.close) + 장기 예측(LONG_PRED_TB) + 설명(LONG_LLM_TB)
# -----------------------------
@router.get("/long")
def predict_long(
    code: str = Query(..., description="ticker 예: 005930"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=60, description="최근 N개월만 조회"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1) STOCK_TB에서 일별 종가를 가져온 뒤
            # 2) 파이썬에서 월말 종가로 리샘플
            # 3) LONG_PRED_TB / LONG_LLM_TB와 trade_date 기준 병합
            sql_actual = """
                SELECT
                    trade_date,
                    close
                FROM STOCK_TB
                WHERE ticker = %s
            """
            actual_params = [code]

            if start_date:
                sql_actual += " AND trade_date >= %s"
                actual_params.append(start_date)

            if end_date:
                sql_actual += " AND trade_date <= %s"
                actual_params.append(end_date)

            sql_actual += " ORDER BY trade_date ASC"

            cur.execute(sql_actual, actual_params)
            actual_rows = cur.fetchall()

            if not actual_rows:
                raise HTTPException(status_code=404, detail="장기 예측을 위한 실제 주가 데이터를 찾을 수 없습니다.")

            df_actual = pd.DataFrame(actual_rows)
            df_actual["trade_date"] = pd.to_datetime(df_actual["trade_date"])
            df_actual["close"] = df_actual["close"].astype(float)

            # 월말 종가 생성
            s = df_actual.set_index("trade_date")["close"]
            try:
                monthly_actual = s.resample("ME").last().dropna()
            except ValueError:
                monthly_actual = s.resample("M").last().dropna()

            df_monthly_actual = monthly_actual.reset_index()
            df_monthly_actual.columns = ["trade_date", "actual"]

            # 예측값/설명 조회
            sql_pred = """
                SELECT
                    p.trade_date         AS trade_date,
                    p.prediction         AS predicted_value,
                    p.shap_feature       AS shap_feature,
                    p.shap_value         AS shap_value,
                    l.interpretation     AS interpretation
                FROM LONG_PRED_TB p
                LEFT JOIN LONG_LLM_TB l
                    ON p.trade_date = l.trade_date
                   AND p.ticker = l.ticker
                WHERE p.ticker = %s
            """
            pred_params = [code]

            if start_date:
                sql_pred += " AND p.trade_date >= %s"
                pred_params.append(start_date)

            if end_date:
                sql_pred += " AND p.trade_date <= %s"
                pred_params.append(end_date)

            sql_pred += " ORDER BY p.trade_date ASC"

            cur.execute(sql_pred, pred_params)
            pred_rows = cur.fetchall()

            df_pred = pd.DataFrame(pred_rows)

            # 예측 데이터가 아예 없더라도 actual만 먼저 보여주고 싶으면 여기서 빈 df 허용 가능
            if df_pred.empty:
                # 현재월 actual만 보여주는 최소 응답
                data = [
                    {
                        "date": _to_month_label(r["trade_date"]),
                        "actual": _safe_float(r["actual"]),
                    }
                    for _, r in df_monthly_actual.iterrows()
                ]

                if limit is not None:
                    data = data[-limit:]

                return {
                    "confidence": 0,
                    "data": data,
                }

            df_pred["trade_date"] = pd.to_datetime(df_pred["trade_date"])

            # 월말 actual + long prediction trade_date 기준 outer merge
            df_merged = pd.merge(
                df_monthly_actual,
                df_pred,
                how="outer",
                on="trade_date",
            ).sort_values("trade_date")

            data = []

            for _, r in df_merged.iterrows():
                point = {
                    "date": _to_month_label(r["trade_date"]),
                }

                if pd.notna(r.get("actual")):
                    point["actual"] = _safe_float(r["actual"])

                # prediction이 단일값일 경우
                if pd.notna(r.get("predicted_value")):
                    point["predicted"] = _safe_float(r["predicted_value"])

                if pd.notna(r.get("shap_feature")) and pd.notna(r.get("shap_value")):
                    point["reason"] = [
                        {
                            "factor": str(r["shap_feature"]),
                            "impact": r.get("interpretation") or "",
                            "contribution": _safe_float(r["shap_value"]),
                        }
                    ]

                if pd.notna(r.get("interpretation")) and r.get("interpretation"):
                    point["changeReason"] = r["interpretation"]

                data.append(point)

                # -----------------------------------------
                # [배열(JSON)로 바뀌는 경우 예시]
                #
                # LONG_PRED_TB.prediction 이 예:
                # [0.03, 0.05, 0.08]
                # 처럼 여러 개월 수익률/예측값 배열이면,
                # 각 값마다 미래 월 포인트를 따로 펼쳐서 append 해야 합니다.
                #
                # 예시:
                #
                # import json
                # preds = r["predicted_value"]
                # if isinstance(preds, str):
                #     preds = json.loads(preds)
                #
                # base_date = pd.to_datetime(r["trade_date"])
                # for idx, pred in enumerate(preds, start=1):
                #     future_date = base_date + pd.DateOffset(months=idx)
                #     data.append({
                #         "date": _to_month_label(future_date),
                #         "predicted": float(pred)
                #     })
                #
                # -----------------------------------------

            if limit is not None:
                data = data[-limit:]

            return {
                "confidence": 0,   # 나중에 별도 컬럼/테이블 생기면 교체
                "data": data,
            }

    finally:
        conn.close()