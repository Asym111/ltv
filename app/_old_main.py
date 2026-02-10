from fastapi import FastAPI

from app.core.database import Base, engine
from app import models  # важно: импорт, чтобы SQLAlchemy "увидел" модели

app = FastAPI(title="LTV Loyalty Platform")


@app.on_event("startup")
def on_startup():
    # Для MVP: создаём таблицы автоматически.
    # Позже заменим на Alembic миграции.
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"status": "ok", "app": "LTV Loyalty Platform"}
