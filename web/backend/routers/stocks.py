from fastapi import APIRouter, Query, HTTPException

from db.database import get_connection

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/")
def list_stocks(
    active_only: bool = Query(True, description="true면 is_active=1 종목만 반환"),
    limit: int = Query(500, ge=1, le=2000),
):
    """
    KOSPI200_STOCKS_TB + SECTOR_TB 조인으로 종목 리스트 반환.
    React Sidebar에서 사용하기 좋게 code/name/sector 형태로 내려줌.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    k.ticker      AS ticker,
                    k.stock_name  AS stock_name,
                    k.sector_code AS sector_code,
                    k.is_active   AS is_active,
                    s.sector_name AS sector_name
                FROM KOSPI200_STOCKS_TB k
                LEFT JOIN SECTOR_TB s
                    ON k.sector_code = s.sector_code
            """
            params = []

            if active_only:
                sql += " WHERE k.is_active = TRUE"

            sql += " ORDER BY k.stock_name ASC LIMIT %s"
            params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()

            return [
                {
                    "code": r["ticker"],
                    "name": r["stock_name"],
                    "sector": r["sector_name"] or "미분류",
                    "sector_code": r["sector_code"],
                    "is_active": bool(r["is_active"]),
                }
                for r in rows
            ]
    finally:
        conn.close()


@router.get("/{code}")
def get_stock(code: str):
    """
    단일 종목 조회 (디버깅/상세페이지용)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    k.ticker      AS ticker,
                    k.stock_name  AS stock_name,
                    k.sector_code AS sector_code,
                    k.is_active   AS is_active,
                    s.sector_name AS sector_name
                FROM KOSPI200_STOCKS_TB k
                LEFT JOIN SECTOR_TB s
                    ON k.sector_code = s.sector_code
                WHERE k.ticker = %s
                LIMIT 1
            """
            cur.execute(sql, (code,))
            r = cur.fetchone()

            if not r:
                raise HTTPException(status_code=404, detail="Stock not found")

            return {
                "code": r["ticker"],
                "name": r["stock_name"],
                "sector": r["sector_name"] or "미분류",
                "sector_code": r["sector_code"],
                "is_active": bool(r["is_active"]),
            }
    finally:
        conn.close()

@router.get("/{code}/prices")
def get_stock_prices(
    code: str,
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=5000, description="가져올 최대 건수"),
):
    """
    특정 종목의 과거/현재 종가 조회
    그래프의 actual 데이터로 사용
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT
                    trade_date,
                    close
                FROM STOCK_TB
                WHERE ticker = %s
            """
            params = [code]

            if start_date:
                sql += " AND trade_date >= %s"
                params.append(start_date)

            if end_date:
                sql += " AND trade_date <= %s"
                params.append(end_date)

            sql += " ORDER BY trade_date ASC"

            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()

            if not rows:
                raise HTTPException(status_code=404, detail="Price data not found")

            return [
                {
                    "date": r["trade_date"].strftime("%Y-%m-%d") if r["trade_date"] else None,
                     "actual": float(r["close"]) if r["close"] is not None else None,
                }
                for r in rows
            ]
    finally:
        conn.close()