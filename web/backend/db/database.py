import os
import pymysql
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME", "STOCK_DB")

    if not user or not password:
        raise ValueError("DB_USER 또는 DB_PASSWORD가 설정되지 않았습니다. .env를 확인하세요.")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor,
    )