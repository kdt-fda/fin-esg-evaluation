from __future__ import annotations

from typing import Any


# 그대로 보여줄 필요 없는 상태형 / 이벤트형 feature
EXCLUDED_FEATURES = {
    "bull_dummy",
    "high_vol_dummy",
    "mkt_regime",
    "bb_breakout",
    "golden_cross_5_20",
    "death_cross_5_20",
    "golden_cross_20_60",
    "death_cross_20_60",
    "msci_event",
    "is_pbr_overheated",
    "is_high_vol_stock",
}


SECTOR_CODE_TO_TABLE = {
    "COMM": "COMM_TB",
    "CONS_DISC": "CONS_DISC_TB",
    "CONS_STAPLES": "CONS_STAPLES_TB",
    "CONSTRUCTION": "CONSTRUCTION_TB",
    "ENER_CHEM": "ENER_CHEM_TB",
    "FINANCE": "FINANCE_TB",
    "HEALTHCARE": "HEALTHCARE_TB",
    "HEAVY_INT": "HEAVY_INT_TB",
    "INDUSTRIALS": "INDUSTRIALS_TB",
    "IT": "IT_TB",
    "MATERIALS": "MATERIALS_TB",
}


def safe_number(value: Any):
    if value is None:
        return None

    try:
        num = float(value)
        if num.is_integer():
            return int(num)
        return num
    except Exception:
        return value


def get_sector_table(cur, ticker: str) -> str | None:
    sql = """
        SELECT sector_code
        FROM KOSPI200_STOCKS_TB
        WHERE ticker = %s
        LIMIT 1
    """
    cur.execute(sql, [ticker])
    row = cur.fetchone()
    if not row:
        return None

    sector_code = row.get("sector_code")
    if not sector_code:
        return None

    return SECTOR_CODE_TO_TABLE.get(sector_code)


def has_column(cur, table_name: str, column_name: str) -> bool:
    sql = """
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
    """
    cur.execute(sql, [table_name, column_name])
    return cur.fetchone() is not None


def resolve_feature_source(cur, ticker: str, feature_key: str) -> tuple[str, bool] | None:
    """
    반환:
    - (table_name, needs_ticker)
    - None: 제외 대상이거나 미지원 feature
    """
    if not feature_key:
        return None

    if feature_key in EXCLUDED_FEATURES:
        return None

    ordered_tables = [
        ("STOCK_TB", True),
        ("COMMON_TB", False),
        ("FUNDAMENTAL_TB", True),
        ("MACROECONOMICS_TB", False),
    ]

    for table_name, needs_ticker in ordered_tables:
        if has_column(cur, table_name, feature_key):
            return (table_name, needs_ticker)

    sector_table = get_sector_table(cur, ticker)
    if sector_table and has_column(cur, sector_table, feature_key):
        return (sector_table, True)

    return None


def fetch_latest_feature_value(cur, ticker: str, feature_key: str):
    """
    feature 하나의 가장 최근 값만 반환
    예: ma5 -> 12000
    """
    source = resolve_feature_source(cur, ticker, feature_key)
    if not source:
        return None

    table_name, needs_ticker = source

    if table_name == "FUNDAMENTAL_TB":
        sql = f"""
            SELECT {feature_key} AS value
            FROM {table_name}
            WHERE ticker = %s
            ORDER BY year DESC, quarter DESC
            LIMIT 1
        """
        cur.execute(sql, [ticker])
        row = cur.fetchone()
        if not row:
            return None
        return safe_number(row["value"])

    if not needs_ticker:
        sql = f"""
            SELECT {feature_key} AS value
            FROM {table_name}
            ORDER BY trade_date DESC
            LIMIT 1
        """
        cur.execute(sql)
        row = cur.fetchone()
        if not row:
            return None
        return safe_number(row["value"])

    sql = f"""
        SELECT {feature_key} AS value
        FROM {table_name}
        WHERE ticker = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    cur.execute(sql, [ticker])
    row = cur.fetchone()
    if not row:
        return None

    return safe_number(row["value"])


def build_feature_contexts(cur, ticker: str, interpretation: dict[str, Any] | None) -> dict[str, Any]:
    """
    interpretation.main_signals[].feature 를 읽어서
    { feature: 최신값 } 형태로 반환

    예:
    {
        "ma5": 12000,
        "macd": 1.23,
        "roe": 8.5
    }
    """
    if not interpretation:
        return {}

    signals = interpretation.get("main_signals") or []
    result: dict[str, Any] = {}

    for signal in signals:
        if not isinstance(signal, dict):
            continue

        feature_key = signal.get("feature_key") or signal.get("feature")
        if not feature_key:
            continue

        if feature_key in result:
            continue

        value = fetch_latest_feature_value(cur, ticker, feature_key)
        if value is None:
            continue

        result[feature_key] = value

    return result