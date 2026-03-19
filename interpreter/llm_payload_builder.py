from __future__ import annotations

from typing import Dict, Any, List
import json
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MAPPING_PATH = BASE_DIR / "feature_mapping.json"

if MAPPING_PATH.exists():
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        FEATURE_MAP = json.load(f)


def parse_shap_factors(model_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_features = model_result.get("shap_feature", [])
    raw_values = model_result.get("shap_value", [])

    features = json.loads(raw_features) if isinstance(raw_features, str) else raw_features
    values = json.loads(raw_values) if isinstance(raw_values, str) else raw_values

    if len(features) != len(values):
        raise ValueError("shap_feature와 shap_value 길이가 다릅니다.")

    return [
        {
            "feature": FEATURE_MAP.get(str(feature), str(feature)),
            "shap_value": float(value),
        }
        for feature, value in zip(features, values)
    ]


def format_factors_for_prompt(factors: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"- feature={f['feature']}, shap_value={f['shap_value']:.4f}"
        for f in factors
    )


def format_prediction_for_prompt(prediction: Any) -> str:
    if prediction is None:
        return "[]"

    if isinstance(prediction, str):
        try:
            parsed = json.loads(prediction)
            return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            return prediction

    return json.dumps(prediction, ensure_ascii=False)


def build_combined_llm_payload(
    short_result: Dict[str, Any],
    long_result: Dict[str, Any],
) -> Dict[str, Any]:
    short_factors = parse_shap_factors(short_result)
    long_factors = parse_shap_factors(long_result)

    short_prediction = short_result.get("prediction")

    if isinstance(short_prediction, list):
        short_prediction = json.dumps(short_prediction, ensure_ascii=False)

    long_score = long_result.get("score")

    return {
        "stock_name": short_result.get("stock_name") or long_result.get("stock_name"),
        "ticker": short_result.get("ticker") or long_result.get("ticker"),
        "short_prediction": format_prediction_for_prompt(short_prediction),
        "long_score": float(long_score) if long_score is not None else None,
        "short_top_factors": format_factors_for_prompt(short_factors),
        "long_top_factors": format_factors_for_prompt(long_factors),
    }


def get_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def load_latest_short_result_from_db(ticker: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    p.ticker,
                    k.stock_name,
                    p.prediction,
                    p.shap_feature,
                    p.shap_value
                FROM SHORT_PRED_TB p
                LEFT JOIN KOSPI200_STOCKS_TB k
                    ON p.ticker = k.ticker
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """
            cur.execute(sql, [ticker])
            row = cur.fetchone()

            if not row:
                raise ValueError(f"SHORT_PRED_TB에서 ticker={ticker} 데이터를 찾지 못했습니다.")

            return {
                "stock_name": row.get("stock_name"),
                "ticker": row.get("ticker"),
                "prediction": row.get("prediction"),
                "shap_feature": row.get("shap_feature"),
                "shap_value": row.get("shap_value"),
            }
    finally:
        conn.close()


def load_latest_long_result_from_db(ticker: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    p.ticker,
                    k.stock_name,
                    p.score,
                    p.shap_feature,
                    p.shap_value
                FROM LONG_PRED_TB p
                LEFT JOIN KOSPI200_STOCKS_TB k
                    ON p.ticker = k.ticker
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """
            cur.execute(sql, [ticker])
            row = cur.fetchone()

            if not row:
                raise ValueError(f"LONG_PRED_TB에서 ticker={ticker} 데이터를 찾지 못했습니다.")

            return {
                "stock_name": row.get("stock_name"),
                "ticker": row.get("ticker"),
                "score": row.get("score"),
                "shap_feature": row.get("shap_feature"),
                "shap_value": row.get("shap_value"),
            }
    finally:
        conn.close()


def build_combined_llm_payload_from_db(ticker: str) -> Dict[str, Any]:
    short_result = load_latest_short_result_from_db(ticker)
    long_result = load_latest_long_result_from_db(ticker)
    return build_combined_llm_payload(short_result, long_result)