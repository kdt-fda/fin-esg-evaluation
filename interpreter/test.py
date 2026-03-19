from __future__ import annotations

import json
from typing import Dict, Any, List

from shap_llm_builder import (
    load_latest_short_result_from_db,
    load_latest_long_result_from_db,
    build_combined_llm_payload,
)
from llm_generator import generate_combined_interpretation


def run_single_ticker(ticker: str) -> Dict[str, Any]:
    """
    단일 종목에 대해
    1) DB에서 최신 short/long 결과 로드
    2) LLM 해석 생성
    3) 결과 반환
    """
    short_result = load_latest_short_result_from_db(ticker)
    long_result = load_latest_long_result_from_db(ticker)

    payload = build_combined_llm_payload(
        short_result=short_result,
        long_result=long_result,
    )

    interpretation = generate_combined_interpretation(
        short_result=short_result,
        long_result=long_result,
    )

    return {
        "ticker": ticker,
        "stock_name": short_result.get("stock_name") or long_result.get("stock_name"),
        "payload": payload,
        "interpretation": interpretation,
    }


def run_multiple_tickers(tickers: List[str]) -> List[Dict[str, Any]]:
    """
    나중에 전체 기업 batch 실행으로 확장하기 쉽게 만든 함수.
    실패한 종목도 함께 기록.
    """
    results: List[Dict[str, Any]] = []

    for ticker in tickers:
        try:
            result = run_single_ticker(ticker)
            results.append({
                "ticker": ticker,
                "success": True,
                "result": result,
            })
        except Exception as e:
            results.append({
                "ticker": ticker,
                "success": False,
                "error": str(e),
            })

    return results


if __name__ == "__main__":
    # 우선 삼성전자 한 종목만 확인
    ticker = "005930"

    result = run_single_ticker(ticker)
    print(json.dumps(result["interpretation"], ensure_ascii=False, indent=2))