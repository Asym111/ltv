import os
import sqlite3
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def _resolve_db_path() -> str:
    # Priority: explicit DB_PATH -> DATABASE_URL sqlite path -> fallback
    db_path = (os.getenv("DB_PATH") or "").strip()
    if db_path:
        return db_path

    db_url = (os.getenv("DATABASE_URL") or "").strip()
    if db_url.startswith("sqlite:///"):
        parsed = urlparse(db_url)
        p = (parsed.path or "").lstrip("/")
        return p or "ltv.db"

    return "ltv.db"


DB_PATH = _resolve_db_path()

COLUMNS = [
    ("bonus_name",                "TEXT NOT NULL DEFAULT 'баллы'"),
    ("welcome_bonus_percent",     "INTEGER NOT NULL DEFAULT 0"),
    ("burn_percent",              "INTEGER NOT NULL DEFAULT 100"),
    ("birthday_notify_7d",        "BOOLEAN NOT NULL DEFAULT 1"),
    ("birthday_notify_3d",        "BOOLEAN NOT NULL DEFAULT 1"),
    ("birthday_notify_1d",        "BOOLEAN NOT NULL DEFAULT 1"),
    ("birthday_message",          "TEXT"),
    ("birthday_message_7d",       "TEXT"),
    ("birthday_enabled",          "BOOLEAN NOT NULL DEFAULT 1"),
    ("tiers_json",                "TEXT"),
    ("boost_enabled",             "BOOLEAN NOT NULL DEFAULT 0"),
    ("boost_percent",             "INTEGER NOT NULL DEFAULT 7"),
    ("boost_always",              "BOOLEAN NOT NULL DEFAULT 0"),
    ("boost_time_from",           "TEXT"),
    ("boost_time_to",             "TEXT"),
    ("boost_mode",                "TEXT NOT NULL DEFAULT 'days'"),
    ("boost_weekdays",            "TEXT"),
    ("boost_dates",               "TEXT"),
    ("cost_per_lead",             "INTEGER NOT NULL DEFAULT 0"),
    ("cost_per_client",           "INTEGER NOT NULL DEFAULT 0"),
]

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Получаем текущие колонки
    cur.execute("PRAGMA table_info(settings)")
    existing = {row[1] for row in cur.fetchall()}

    added = []
    for col_name, col_def in COLUMNS:
        if col_name not in existing:
            sql = f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}"
            cur.execute(sql)
            added.append(col_name)
            print(f"  [OK] Added column: {col_name}")
        else:
            print(f"  [SKIP] Exists: {col_name}")

    conn.commit()
    conn.close()

    if added:
        print(f"\nMigration complete. Columns added: {len(added)}")
    else:
        print("\nMigration complete. Nothing to add.")

if __name__ == "__main__":
    print(f"Run settings migration for DB: {DB_PATH}\n")
    migrate()
