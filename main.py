# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.database import engine, Base

from app.api.users import router as users_router
from app.api.transactions import router as transactions_router
from app.api.crm import router as crm_router
from app.api.settings import router as settings_router
from app.api.ai import router as ai_router
from app.api.analytics import router as analytics_router
from app.api.campaigns import router as campaigns_router  # ✅ NEW

from app.web.admin import router as admin_router
from app.web.admin_campaigns import router as admin_campaigns_router  # ✅ NEW

# ✅ чтобы SQLAlchemy увидел модели (включая Campaign/CampaignRecipient)
import app.models  # noqa: F401
import app.models.campaign  # noqa: F401

app = FastAPI(title="LTV Loyalty Platform")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")

# -------------------------
# API
# -------------------------
app.include_router(users_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
app.include_router(crm_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(campaigns_router, prefix="/api")  # ✅ NEW

# -------------------------
# Admin pages (Jinja)
# -------------------------
app.include_router(admin_router)
app.include_router(admin_campaigns_router)  # ✅ NEW


@app.get("/")
def root():
    return {"status": "ok"}
