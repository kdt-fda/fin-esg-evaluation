from __future__ import annotations

from typing import Dict, Any, List
import json
import os

import pymysql
from dotenv import load_dotenv

load_dotenv()


FEATURE_LABELS = {
    "revenue": "매출액",
    "revenue_growth": "매출 성장률",
    "operating_income": "영업이익",
    "operating_margin": "영업이익률",
    "net_income": "순이익",
    "depreciation": "감가상각비",
    "ebitda": "EBITDA",
    "equity": "자기자본",
    "assets": "총자산",
    "liabilities": "총부채",
    "cash": "현금성자산",
    "roe": "자기자본이익률(ROE)",
    "roa": "총자산이익률(ROA)",
    "debt_ratio": "부채비율",
    "cfo": "영업현금흐름",
    "capex": "설비투자",
    "fcf": "잉여현금흐름",
    "per": "PER",
    "pbr": "PBR",
    "market_cap": "시가총액",
    "ev": "EV",
    "ev_ebitda": "EV/EBITDA",
    "Foreign_Net_Amt": "외국인 순매수",
    "Inst_Net_Amt": "기관 순매수",
    "Indiv_Net_Amt": "개인 순매수",
    "MA60": "60일 이동평균",
    "MA120": "120일 이동평균",
    "Golden_Cross_20_60": "20일선-60일선 골든크로스",
    "Death_Cross_20_60": "20일선-60일선 데드크로스",
    "ma5": "5일 이동평균",
    "ma20": "20일 이동평균",
    "foreign_net_amt": "외국인 순매수",
    "inst_net_amt": "기관 순매수",
    "rsi": "RSI",
    "macd": "MACD",
    "macd_signal": "MACD 시그널",
    "bb_upper": "볼린저 상단",
    "bb_lower": "볼린저 하단",
    "bb_breakout": "볼린저 돌파",
    "golden_cross_5_20": "5일선-20일선 골든크로스",
    "death_cross_5_20": "5일선-20일선 데드크로스",
    "msci_event": "MSCI 이벤트",
    "gdp_growth": "GDP 성장률",
    "manufacturing_pmi": "제조업 PMI",
    "us_cpi": "미국 CPI",
    "kr_cpi": "한국 CPI",
    "us_core_cpi": "미국 근원 CPI",
    "us_core_pce": "미국 근원 PCE",
    "us_init_claims": "미국 신규실업수당청구",
    "us_unrate": "미국 실업률",
    "kr_unrate": "한국 실업률",
    "export_yoy": "수출 증가율",
    "import_yoy": "수입 증가율",
    "trade_yoy": "수출입 증가율",
    "us_ust_3y": "미국 3년 국채금리",
    "us_ust_10y": "미국 10년 국채금리",
    "usdkrw": "원달러 환율",
    "wti": "WTI 유가",
    "brent": "브렌트 유가",
    "Sector": "업종 요인",
}


def to_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature)


def parse_shap_factors(model_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_features = model_result.get("shap_feature", [])
    raw_values = model_result.get("shap_value", [])

    features = json.loads(raw_features) if isinstance(raw_features, str) else raw_features
    values = json.loads(raw_values) if isinstance(raw_values, str) else raw_values

    if len(features) != len(values):
        raise ValueError("shap_feature와 shap_value 길이가 다릅니다.")

    return [
        {
            "feature": feature,
            "label": to_label(feature),
            "shap_value": float(value),
        }
        for feature, value in zip(features, values)
    ]


def format_factors_for_prompt(factors: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"- {f['label']} ({f['feature']}): {f['shap_value']:.4f}"
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