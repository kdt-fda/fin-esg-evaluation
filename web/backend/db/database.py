import os
import pymysql
from dotenv import load_dotenv
from dbutils.pooled_db import PooledDB

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "STOCK_DB")

if not DB_USER or not DB_PASSWORD:
    raise ValueError("DB_USER 또는 DB_PASSWORD가 설정되지 않았습니다. .env를 확인하세요.")

if not DB_HOST:
    raise ValueError("DB_HOST가 설정되지 않았습니다. .env를 확인하세요.")

POOL = PooledDB(
    creator=pymysql,
    maxconnections=5,
    mincached=1,
    maxcached=3,
    maxshared=3,
    blocking=True,
    ping=1,
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
    charset="utf8mb4",
)

def get_connection():
    return POOL.connection()