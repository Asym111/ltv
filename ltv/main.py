from fastapi import FastAPI

from app.core.database import Base, engine
from app import models  # noqa: F401
from app.api import users_router, transactions_router

app = FastAPI(title="LTV Loyalty Platform")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


app.include_router(users_router)
app.include_router(transactions_router)


@app.get("/")
def root():
    return {"status": "ok", "app": "LTV Loyalty Platform"}
