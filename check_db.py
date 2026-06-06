"""
DB 연결 확인 스크립트
- DATABASE_URL 있으면 PostgreSQL, 없으면 로컬 SQLite
- 주요 테이블 row 수 출력
"""
from common import get_db_connection, is_postgres

TABLES = ["alert_log", "price_snapshot", "trade_event", "equity_snapshot"]


def count_rows(conn, table):
    try:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) FROM {table}")
        return c.fetchone()[0]
    except Exception as e:
        return f"없음 ({e.__class__.__name__})"


def main():
    db_type = "PostgreSQL" if is_postgres() else "SQLite (로컬)"
    print("=" * 45)
    print(f"DB 연결: {db_type}")
    print("=" * 45)

    conn = get_db_connection()
    for table in TABLES:
        count = count_rows(conn, table)
        print(f"  {table:<22} : {count} rows")
    conn.close()

    print("=" * 45)


if __name__ == "__main__":
    main()
