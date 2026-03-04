from fastapi import APIRouter, Query, HTTPException
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _connect():
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME", "STOCK_DB")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
    )


@router.get("/")
def list_stocks(
    active_only: bool = Query(True, description="true면 is_active=1 종목만 반환"),
    limit: int = Query(500, ge=1, le=2000),
):
    """
    KOSPI200_STOCKS_TB + SECTOR_TB 조인으로 종목 리스트 반환.
    React Sidebar에서 사용하기 좋게 code/name/sector 형태로 내려줌.
    """
    conn = _connect()
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

            # 프론트가 쓰기 편하게 key명 정리
            return [
                {
                    "code": r["ticker"],
                    "name": r["stock_name"],
                    "sector": r["sector_name"] or "미분류",  # sector가 없을 때 fallback
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
    conn = _connect()
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