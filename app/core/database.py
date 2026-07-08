from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Для SQLite нужно check_same_thread=False
connect_args = {}
db_url = settings.DATABASE_URL

if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
)

if db_url.startswith("sqlite"):
    # WAL: фоновый воркер рассылок пишет параллельно с запросами без "database is locked"
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
