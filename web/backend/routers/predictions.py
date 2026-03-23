from fastapi import APIRouter, HTTPException, Query
import json
import pandas as pd

from db.database import get_connection

router = APIRouter(prefix="/predictions", tags=["predictions"])


FEATURE_LABEL_MAP = {
    "trade_date": "거래일자",
    "ticker": "종목코드",
    "stock_name": "종목명",
    "open": "시가",
    "high": "고가",
    "low": "저가",
    "close": "종가",
    "volume": "거래량",
    "short_balance": "공매도금액",
    "news_score": "뉴스 감성 점수",
    "usdkrw": "원/달러 환율",
    "wti": "WTI유 가격",
    "brent": "브렌트유 가격",
    "close_kospi200": "KOSPI200 지수",
    "bull_dummy": "상승 국면 여부",
    "mkt_ret": "시장 수익률",
    "mkt_vol_20": "20일 시장 변동성",
    "vol_threshold": "고변동성 임계치",
    "high_vol_dummy": "고변동성 국면 여부",
    "mkt_regime": "시장 국면",
    "cli": "경기선행지수(CLI)",
    "cli_lag1": "경기선행지수(1개월 지연)",
    "cli_lag3": "경기선행지수(3개월 지연)",
    "cli_lag6": "경기선행지수(6개월 지연)",
    "ma5": "5일 이동평균선",
    "ma20": "20일 이동평균선",
    "foreign_net_amt": "외국인 순매수",
    "inst_net_amt": "기관 순매수",
    "rsi": "RSI(상대강도지수)",
    "macd": "MACD 추세",
    "macd_signal": "MACD 시그널",
    "bb_upper": "볼린저밴드 상단",
    "bb_lower": "볼린저밴드 하단",
    "bb_breakout": "볼린저밴드 돌파",
    "golden_cross_5_20": "단기 골든크로스(5-20일)",
    "death_cross_5_20": "단기 데드크로스(5-20일)",
    "msci_event": "MSCI 지수 편입/편출",
    "ma60": "60일 이동평균선",
    "ma120": "120일 이동평균선",
    "ma200": "200일 이동평균선",
    "golden_cross_20_60": "중기 골든크로스(20-60일)",
    "death_cross_20_60": "중기 데드크로스(20-60일)",
    "revenue": "매출액",
    "revenue_growth": "매출액 증가율",
    "operating_income": "영업이익",
    "operating_margin": "영업이익률",
    "net_income": "당기순이익",
    "depreciation": "감가상각비",
    "rnd_expense": "연구개발(R&D) 비용",
    "roe": "자기자본수익률(ROE)",
    "roa": "총자산수익률(ROA)",
    "debt_ratio": "부채비율",
    "shares": "발행주식수",
    "market_cap": "시가총액",
    "per": "주가수익비율(PER)",
    "pbr": "주가순자산비율(PBR)",
    "ebitda": "EBITDA",
    "ev_ebitda": "EV/EBITDA",
    "us_cpi": "미국 소비자물가지수(CPI)",
    "us_core_cpi": "미국 근원 CPI",
    "us_core_pce": "미국 근원 PCE",
    "us_unrate": "미국 실업률",
    "us_init_claims": "미국 신규 실업수당 청구건수",
    "us_policy_rate": "미국 기준금리",
    "base_rate": "한국 기준금리",
    "us_ust_3y": "미국 국채 3년물 금리",
    "us_ust_10y": "미국 국채 10년물 금리",
    "ktb3y": "한국 국고채 3년물 금리",
    "ktb10y": "한국 국고채 10년물 금리",
    "kr_cpi": "한국 소비자물가지수(CPI)",
    "unemployment_rate": "한국 실업률",
    "ccsi": "소비자심리지수(CCSI)",
    "export_total": "총 수출액",
    "export_yoy": "수출액 전년비 증감률",
    "import_total": "총 수입액",
    "import_yoy": "수입액 전년비 증감률",
    "gdp_level": "GDP 규모",
    "gdp_qoq": "GDP 전분기비 성장률",
    "jpy3": "일본 국채 3년물 금리",
    "jpy10": "일본 국채 10년물 금리",
    "pmi": "구매관리자지수(PMI)",
    "rate_diff_policy": "한미 기준금리 격차",
    "rate_diff_3y": "한미 3년물 금리 격차",
    "rate_diff_10y": "한미 10년물 금리 격차",
    "corr_ndx": "나스닥 상관계수",
    "interest_beta": "금리 민감도",
    "z_score": "산업 상대가치 Z-score",
    "purchasing_power_mom": "소득 모멘텀",
    "durables_ir_beta": "금리 민감도",
    "csi_sentiment": "소비자심리지수(2개월 지연)",
    "real_revenue_growth": "실질 매출 성장률",
    "ebitda_margin": "EBITDA 마진",
    "fx_correlation": "환율 상관성",
    "bsi_momentum": "건설업 BSI 모멘텀",
    "mfg_lag3": "제조업 지수(3개월 지연)",
    "spread_momentum": "에틸렌-나프타 스프레드 모멘텀",
    "mfg_lag6": "제조업 지수(6개월 지연)",
    "oil_beta": "유가 민감도",
    "vix_corr": "VIX(공포지수) 상관계수",
    "global_fin_beta": "글로벌 금융 민감도",
    "rnd_ratio": "R&D 비율",
    "pbr_zscore": "PBR 상대가치 Z-score",
    "is_pbr_overheated": "PBR 고평가 국면 여부",
    "vol_ratio": "시장 대비 변동성 비율",
    "is_high_vol_stock": "고변동성 종목 여부",
    "fx_beta": "환율 민감도",
    "mfg_momentum": "제조업 지수 모멘텀",
    "energy_momentum": "유가 추세 모멘텀",
    "logistics_momentum": "물류 업황 모멘텀",
    "ship_vol_lag3": "운송 매출 지수(3개월 지연)",
    "soxx_corr": "글로벌 반도체 지수 상관계수",
    "apple_momentum": "글로벌 IT 수요 모멘텀",
    "mfg_cycle_momentum": "글로벌 제조 사이클 모멘텀",
    "china_momentum": "중국 대형주 시장 모멘텀",
    "copper_beta": "구리 가격 민감도",
    "steel_beta": "철강 가격 민감도",
}

FEATURE_REVERSE_MAP = {label: key for key, label in FEATURE_LABEL_MAP.items()}


def _to_ymd(value) -> str:
    if value is None:
        return ""
    return pd.to_datetime(value).strftime("%Y-%m-%d")


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


def _build_shap_map(shap_features, shap_values) -> dict[str, float | None]:
    parsed_features = _safe_json(shap_features)
    parsed_values = _safe_json(shap_values)

    if not isinstance(parsed_features, list) or not isinstance(parsed_values, list):
        return {}

    result: dict[str, float | None] = {}

    for feature, value in zip(parsed_features, parsed_values):
        if feature is None:
            continue
        result[str(feature)] = _safe_float(value)

    return result


def _augment_interpretation(interpretation, shap_map=None):
    if not isinstance(interpretation, dict):
        return interpretation

    main_signals = interpretation.get("main_signals")
    if not isinstance(main_signals, list):
        return interpretation

    shap_map = shap_map or {}
    copied = dict(interpretation)
    augmented_signals = []

    for signal in main_signals:
        if not isinstance(signal, dict):
            augmented_signals.append(signal)
            continue

        signal_copy = dict(signal)
        feature_label = signal_copy.get("feature")
        feature_key = FEATURE_REVERSE_MAP.get(feature_label, feature_label)

        signal_copy["feature_key"] = feature_key
        signal_copy["shap_value"] = shap_map.get(feature_key)
        augmented_signals.append(signal_copy)

    copied["main_signals"] = augmented_signals
    return copied


def _get_latest_close(cur, code: str):
    sql = """
        SELECT trade_date, close
        FROM STOCK_TB
        WHERE ticker = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    cur.execute(sql, [code])
    row = cur.fetchone()

    if not row or row.get("close") is None:
        return None

    return _safe_float(row["close"])


def _build_short_payload(cur, code: str):
    latest_close = _get_latest_close(cur, code)

    sql = """
        SELECT
            p.pred_date      AS pred_date,
            p.prediction     AS predicted_value,
            p.conf_score     AS conf_score,
            p.shap_feature   AS shap_feature,
            p.shap_value     AS shap_value
        FROM SHORT_PRED_TB p
        WHERE p.ticker = %s
        ORDER BY p.pred_date DESC
        LIMIT 1
    """
    cur.execute(sql, [code])
    row = cur.fetchone()

    if not row:
        return {
            "pred_date": None,
            "confidence": 0,
            "pastCount": 0,
            "data": [],
            "shap_map": {},
        }

    pred_date = _to_ymd(row.get("pred_date"))
    confidence = _safe_float(row.get("conf_score")) or 0
    shap_map = _build_shap_map(row.get("shap_feature"), row.get("shap_value"))

    return_list = _extract_return_list(row.get("predicted_value"))
    if latest_close is None or not return_list:
        return {
            "pred_date": pred_date,
            "confidence": confidence,
            "pastCount": 0,
            "data": [],
            "shap_map": shap_map,
        }

    base_date = pd.to_datetime(row["pred_date"])
    data = []

    for i, predicted_return in enumerate(return_list, start=1):
        predicted_price = latest_close * (1 + (predicted_return / 100.0))
        target_date = base_date + pd.offsets.BDay(i)

        data.append({
            "date": target_date.strftime("%Y-%m-%d"),
            "predicted": round(predicted_price, 2),
        })

    return {
        "pred_date": pred_date,
        "confidence": confidence,
        "pastCount": 0,
        "data": data,
        "shap_map": shap_map,
    }


def _build_short_interpretation(cur, code: str, shap_map: dict):
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
            "pred_date": None,
            "interpretation": None,
        }

    interpretation = _safe_json(row["interpretation"])
    interpretation = _augment_interpretation(interpretation, shap_map)

    return {
        "pred_date": _to_ymd(row["pred_date"]),
        "interpretation": interpretation,
    }


def _build_long_payload(cur, code: str):
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

    long_pred_sql = """
        SELECT
            p.pred_date      AS pred_date,
            p.conf_score     AS conf_score,
            p.shap_feature   AS shap_feature,
            p.shap_value     AS shap_value
        FROM LONG_PRED_TB p
        WHERE p.ticker = %s
        ORDER BY p.pred_date DESC
        LIMIT 1
    """
    cur.execute(long_pred_sql, [code])
    row = cur.fetchone()

    if not row:
        return {
            "pred_date": None,
            "confidence": 0,
            "data": [],
            "shap_map": {},
            "sector_code": sector_code,
            "sector_name": sector_name,
        }

    pred_date = row.get("pred_date")
    confidence = _safe_float(row.get("conf_score")) or 0
    shap_map = _build_shap_map(row.get("shap_feature"), row.get("shap_value"))

    ranking_data = []
    if sector_code and pred_date:
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
        cur.execute(ranking_sql, [pred_date, sector_code])
        rows = cur.fetchall()

        for r in rows:
            if r.get("score") is None:
                continue

            ranking_data.append({
                "code": r["code"],
                "name": r["name"],
                "sector": r["sector"] or sector_name or "",
                "score": _safe_float(r["score"]),
            })

    return {
        "pred_date": _to_ymd(pred_date),
        "confidence": confidence,
        "data": ranking_data,
        "shap_map": shap_map,
        "sector_code": sector_code,
        "sector_name": sector_name,
    }


def _build_long_interpretation(cur, code: str, shap_map: dict):
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
            "pred_date": None,
            "interpretation": None,
        }

    interpretation = _safe_json(row["interpretation"])
    interpretation = _augment_interpretation(interpretation, shap_map)

    return {
        "pred_date": _to_ymd(row["pred_date"]),
        "interpretation": interpretation,
    }


@router.get("/short/full")
def get_short_full(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            short_payload = _build_short_payload(cur, code)
            interpretation_payload = _build_short_interpretation(
                cur, code, short_payload["shap_map"]
            )

            return {
                "ticker": code,
                "pred_date": short_payload["pred_date"] or interpretation_payload["pred_date"],
                "short": {
                    "confidence": short_payload["confidence"],
                    "pastCount": short_payload["pastCount"],
                    "data": short_payload["data"],
                },
                "interpretation": interpretation_payload["interpretation"],
            }
    finally:
        conn.close()


@router.get("/long/full")
def get_long_full(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            long_payload = _build_long_payload(cur, code)
            interpretation_payload = _build_long_interpretation(
                cur, code, long_payload["shap_map"]
            )

            return {
                "ticker": code,
                "pred_date": long_payload["pred_date"] or interpretation_payload["pred_date"],
                "long": {
                    "confidence": long_payload["confidence"],
                    "data": long_payload["data"],
                },
                "interpretation": interpretation_payload["interpretation"],
            }
    finally:
        conn.close()