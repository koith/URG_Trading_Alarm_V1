import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "urg_settings.json"
PORTFOLIO_PATH = BASE_DIR / "portfolio.json"
STATE_PATH = BASE_DIR / "alert_state.json"
LOG_DB_PATH = BASE_DIR / "urg_log.db"
ENV_PATH = BASE_DIR / ".env"


def is_postgres() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def get_db_connection():
    """DATABASE_URL 있으면 PostgreSQL, 없으면 로컬 SQLite."""
    if is_postgres():
        import psycopg2
        return psycopg2.connect(os.environ["DATABASE_URL"])
    import sqlite3
    return sqlite3.connect(LOG_DB_PATH)


def get_placeholder() -> str:
    """SQL 파라미터 플레이스홀더: PostgreSQL=%s, SQLite=?"""
    return "%s" if is_postgres() else "?"


def load_dotenv():
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def read_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"파일 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def usd(value):
    return f"${value:,.4f}"
