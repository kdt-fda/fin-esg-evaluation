from fastapi import APIRouter, HTTPException, Query
import json
import pandas as pd

from db.database import get_connection

router = APIRouter(prefix="/predictions", tags=["predictions"])


# -----------------------------
# feature 라벨 매핑
# interpretation.main_signals[].feature 가 한글 라벨로 저장된 경우
# raw feature key 를 다시 찾기 위해 사용
# -----------------------------
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


def _build_shap_map(shap_features, shap_values) -> dict[str, float | None]:
    """
    shap_feature / shap_value JSON을 읽어서
    { raw_feature_key: shap_value } 형태 dict 생성
    """
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
    """
    interpretation.main_signals 구조는 유지하면서:
    1) feature(한글 라벨) -> feature_key(raw key) 추가
    2) shap_map 에서 대응 shap_value 추가

    예:
    {
        "feature": "고변동성 임계치",
        "feature_key": "vol_threshold",
        "shap_value": 0.1234,
        ...
    }
    """
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
# + feature_key / shap_value 를 signal 별로 보강
# -----------------------------
@router.get("/short/interpretation")
def get_short_interpretation(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            llm_sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM SHORT_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(llm_sql, [code])
            llm_row = cur.fetchone()

            if not llm_row:
                return {
                    "ticker": code,
                    "pred_date": None,
                    "interpretation": None,
                }

            shap_sql = """
                SELECT
                    p.shap_feature AS shap_feature,
                    p.shap_value   AS shap_value
                FROM SHORT_PRED_TB p
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """
            cur.execute(shap_sql, [code])
            shap_row = cur.fetchone()

            shap_map = {}
            if shap_row:
                shap_map = _build_shap_map(
                    shap_row.get("shap_feature"),
                    shap_row.get("shap_value"),
                )

            interpretation = _safe_json(llm_row["interpretation"])
            interpretation = _augment_interpretation(interpretation, shap_map)

            return {
                "ticker": code,
                "pred_date": _to_ymd(llm_row["pred_date"]),
                "interpretation": interpretation,
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
# + feature_key / shap_value 를 signal 별로 보강
# -----------------------------
@router.get("/long/interpretation")
def get_long_interpretation(
    code: str = Query(..., description="ticker 예: 005930"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            llm_sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM LONG_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(llm_sql, [code])
            llm_row = cur.fetchone()

            if not llm_row:
                return {
                    "ticker": code,
                    "pred_date": None,
                    "interpretation": None,
                }

            shap_sql = """
                SELECT
                    p.shap_feature AS shap_feature,
                    p.shap_value   AS shap_value
                FROM LONG_PRED_TB p
                WHERE p.ticker = %s
                ORDER BY p.pred_date DESC
                LIMIT 1
            """
            cur.execute(shap_sql, [code])
            shap_row = cur.fetchone()

            shap_map = {}
            if shap_row:
                shap_map = _build_shap_map(
                    shap_row.get("shap_feature"),
                    shap_row.get("shap_value"),
                )

            interpretation = _safe_json(llm_row["interpretation"])
            interpretation = _augment_interpretation(interpretation, shap_map)

            return {
                "ticker": code,
                "pred_date": _to_ymd(llm_row["pred_date"]),
                "interpretation": interpretation,
            }
    finally:
        conn.close()


@router.get("/short/full")
def get_short_full(
    code: str = Query(..., description="ticker 예: 005930"),
):
    """
    단기 예측 + 단기 해석을 한 번에 반환
    기존:
      - /predictions/short
      - /predictions/short/interpretation
    을 하나로 합친 API
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1) 최신 종가
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

            latest_close = None
            if latest_price_row and latest_price_row.get("close") is not None:
                latest_close = _safe_float(latest_price_row["close"])

            # 2) short prediction 최신값
            short_pred_sql = """
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
            cur.execute(short_pred_sql, [code])
            short_pred_row = cur.fetchone()

            short_confidence = 0
            short_data = []
            pred_date = None
            shap_map = {}

            if short_pred_row:
                pred_date = _to_ymd(short_pred_row.get("pred_date"))
                short_confidence = _safe_float(short_pred_row.get("conf_score")) or 0

                shap_map = _build_shap_map(
                    short_pred_row.get("shap_feature"),
                    short_pred_row.get("shap_value"),
                )

                return_list = _extract_return_list(short_pred_row.get("predicted_value"))

                if latest_close is not None and return_list:
                    base_date = pd.to_datetime(short_pred_row["pred_date"])

                    for i, predicted_return in enumerate(return_list, start=1):
                        predicted_price = latest_close * (1 + (predicted_return / 100.0))
                        target_date = base_date + pd.offsets.BDay(i)

                        short_data.append({
                            "date": target_date.strftime("%Y-%m-%d"),
                            "predicted": round(predicted_price, 2),
                        })

            # 3) short interpretation 최신값
            short_llm_sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM SHORT_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(short_llm_sql, [code])
            short_llm_row = cur.fetchone()

            interpretation = None
            interpretation_pred_date = None

            if short_llm_row:
                interpretation_pred_date = _to_ymd(short_llm_row.get("pred_date"))
                interpretation = _safe_json(short_llm_row.get("interpretation"))
                interpretation = _augment_interpretation(interpretation, shap_map)

            return {
                "ticker": code,
                "pred_date": pred_date or interpretation_pred_date,
                "short": {
                    "confidence": short_confidence,
                    "pastCount": 0,
                    "data": short_data,
                },
                "interpretation": interpretation,
            }

    finally:
        conn.close()


@router.get("/long/full")
def get_long_full(
    code: str = Query(..., description="ticker 예: 005930"),
):
    """
    장기 예측 + 장기 해석을 한 번에 반환
    기존:
      - /predictions/long
      - /predictions/long/interpretation
    을 하나로 합친 API
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1) 선택 종목 / 섹터 정보
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

            # 2) 선택 종목의 최신 long prediction row
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
            long_pred_row = cur.fetchone()

            if not long_pred_row:
                return {
                    "ticker": code,
                    "pred_date": None,
                    "long": {
                        "confidence": 0,
                        "data": [],
                    },
                    "interpretation": None,
                }

            latest_pred_date = long_pred_row.get("pred_date")
            confidence = _safe_float(long_pred_row.get("conf_score")) or 0

            shap_map = _build_shap_map(
                long_pred_row.get("shap_feature"),
                long_pred_row.get("shap_value"),
            )

            # 3) 같은 섹터 종목 랭킹
            ranking_data = []

            if sector_code and latest_pred_date:
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

                for r in rows:
                    if r.get("score") is None:
                        continue

                    ranking_data.append({
                        "code": r["code"],
                        "name": r["name"],
                        "sector": r["sector"] or sector_name or "",
                        "score": _safe_float(r["score"]),
                    })

            # 4) long interpretation
            long_llm_sql = """
                SELECT
                    l.pred_date      AS pred_date,
                    l.interpretation AS interpretation
                FROM LONG_LLM_TB l
                WHERE l.ticker = %s
                ORDER BY l.pred_date DESC
                LIMIT 1
            """
            cur.execute(long_llm_sql, [code])
            long_llm_row = cur.fetchone()

            interpretation = None
            interpretation_pred_date = None

            if long_llm_row:
                interpretation_pred_date = _to_ymd(long_llm_row.get("pred_date"))
                interpretation = _safe_json(long_llm_row.get("interpretation"))
                interpretation = _augment_interpretation(interpretation, shap_map)

            return {
                "ticker": code,
                "pred_date": _to_ymd(latest_pred_date) or interpretation_pred_date,
                "long": {
                    "confidence": confidence,
                    "data": ranking_data,
                },
                "interpretation": interpretation,
            }

    finally:
        conn.close()