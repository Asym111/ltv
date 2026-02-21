# main.py
import os
from datetime import datetime
from urllib.parse import quote

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from app.core.database import engine, Base, SessionLocal

from app.api.users import router as users_router
from app.api.transactions import router as transactions_router
from app.api.crm import router as crm_router
from app.api.settings_api import router as settings_router
from app.api.ai import router as ai_router
from app.api.analytics import router as analytics_router
from app.api.campaigns import router as campaigns_router
from app.api.accounts_api import router as accounts_router
from app.api.videos_api import router as videos_router
from app.api.whatsapp import router as whatsapp_router

from app.web.admin import router as admin_router
from app.web.admin_campaigns import router as admin_campaigns_router
from app.web.auth import router as auth_router
from app.web.admin_accounts_web import router as admin_accounts_router
from app.web.admin_videos_web import router as admin_videos_router
from app.web.admin_whatsapp import router as admin_whatsapp_router  
from app.web.superadmin import router as superadmin_router  

# ✅ чтобы SQLAlchemy увидел модели
import app.models  # noqa: F401
import app.models.campaign  # noqa: F401
import app.models.auth  # noqa: F401

app = FastAPI(title="LTV Loyalty Platform")

# -------------------------
# DB init
# -------------------------
Base.metadata.create_all(bind=engine)

# -------------------------
# Static
# -------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except Exception:
        return default


AUTH_REMEMBER_DAYS = _int_env("AUTH_REMEMBER_DAYS", 30)
SESSION_SECRET = (os.getenv("SESSION_SECRET", "") or "").strip()
COOKIE_SECURE = (os.getenv("COOKIE_SECURE", "0") or "0").strip() == "1"


# ПАТЧ для main.py — заменить AuthGuardMiddleware.dispatch
# Добавляет проверку ролей на уровне middleware
# Вставить ВМЕСТО существующего класса AuthGuardMiddleware

# ПАТЧ для main.py — заменить AuthGuardMiddleware.dispatch
# Добавляет проверку ролей на уровне middleware
# Вставить ВМЕСТО существующего класса AuthGuardMiddleware

class AuthGuardMiddleware(BaseHTTPMiddleware):
    # Страницы только для owner
    OWNER_ONLY_PATHS = (
        "/admin/settings",
        "/admin/accounts",
        "/api/settings",
    )
    # Страницы для admin + owner
    ADMIN_PLUS_PATHS = (
        "/admin/analytics",
        "/admin/campaigns",
        "/admin/whatsapp",
        "/api/analytics",
        "/api/campaigns",
        "/api/whatsapp",
        "/api/ai",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Публичные пути — без проверок
        if (
            path.startswith("/static")
            or path.startswith("/dev")
            or path in ("/auth", "/auth/", "/logout", "/logout/", "/health", "/favicon.ico")
            or path.startswith("/superadmin")
            or path.startswith("/docs")
            or path.startswith("/openapi.json")
        ):
            return await call_next(request)

        sess = request.session or {}
        uid = sess.get("uid")

        if uid:
            request.state.user = {
                "id":        sess.get("uid"),
                "phone":     sess.get("phone"),
                "name":      sess.get("name"),
                "role":      sess.get("role"),
                "tenant_id": sess.get("tenant_id"),
            }
        else:
            request.state.user = None

        # Проверка авторизации
        if path.startswith("/admin") or path.startswith("/api"):
            if not uid:
                if path.startswith("/api"):
                    return JSONResponse({"detail": "Not authenticated"}, status_code=401)
                next_url = request.url.path
                if request.url.query:
                    next_url += "?" + request.url.query
                return RedirectResponse(
                    url=f"/auth?next={quote(next_url)}",
                    status_code=303,
                )

            # Проверка активности тенанта
            tenant_id = sess.get("tenant_id")
            if tenant_id:
                from app.models.auth import Tenant
                db = SessionLocal()
                try:
                    t = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
                    if not t or not bool(getattr(t, "is_active", False)):
                        request.session.clear()
                        if path.startswith("/api"):
                            return JSONResponse({"detail": "Account disabled"}, status_code=403)
                        return RedirectResponse(
                            url=f"/auth?next={quote('/admin')}&e=disabled",
                            status_code=303,
                        )

                    access_until = getattr(t, "access_until", None)
                    if access_until is not None and access_until < datetime.utcnow():
                        request.session.clear()
                        if path.startswith("/api"):
                            return JSONResponse({"detail": "Subscription expired"}, status_code=402)
                        next_url = request.url.path
                        if request.url.query:
                            next_url += "?" + request.url.query
                        return RedirectResponse(
                            url=f"/auth?next={quote(next_url)}&e=expired",
                            status_code=303,
                        )
                finally:
                    db.close()

            # ── Проверка ролей ───────────────────────────────
            role = str(sess.get("role") or "staff").lower()

            # owner_only страницы
            if any(path.startswith(p) for p in self.OWNER_ONLY_PATHS):
                if role != "owner":
                    if path.startswith("/api"):
                        return JSONResponse(
                            {"detail": "Доступ запрещён. Требуется роль: owner"},
                            status_code=403,
                        )
                    # Для web — редирект на desktop с сообщением
                    return RedirectResponse(url="/admin?e=forbidden", status_code=303)

            # admin+ страницы
            if any(path.startswith(p) for p in self.ADMIN_PLUS_PATHS):
                if role not in ("owner", "admin"):
                    if path.startswith("/api"):
                        return JSONResponse(
                            {"detail": "Доступ запрещён. Требуется роль: admin или owner"},
                            status_code=403,
                        )
                    return RedirectResponse(url="/admin?e=forbidden", status_code=303)

        return await call_next(request)

# IMPORTANT: SessionMiddleware должен быть outermost (добавлен ПОСЛЕДНИМ)
app.add_middleware(AuthGuardMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or "dev-secret-change-me",
    max_age=60 * 60 * 24 * AUTH_REMEMBER_DAYS,
    same_site="lax",
    https_only=COOKIE_SECURE,
)


@app.on_event("startup")
def bootstrap_owner():
    from app.models.auth import Tenant, AuthUser
    from app.core.security import normalize_phone, hash_password

    owner_phone = (os.getenv("OWNER_PHONE", "") or "").strip()
    owner_password = (os.getenv("OWNER_PASSWORD", "") or "")
    owner_name = (os.getenv("OWNER_NAME", "Owner") or "Owner").strip()

    db = SessionLocal()
    try:
        existing = db.query(AuthUser).count()
        if existing > 0:
            print("[BOOTSTRAP] Users already exist. Skip owner create.")
            return

        if not owner_phone or not owner_password:
            print("[BOOTSTRAP] No OWNER_PHONE/OWNER_PASSWORD. Owner not created.")
            return

        tenant = Tenant(name="Default account", is_active=True)
        db.add(tenant)
        db.flush()

        salt, pw_hash = hash_password(owner_password)
        user = AuthUser(
            tenant_id=tenant.id,
            phone=normalize_phone(owner_phone),
            name=owner_name,
            role="owner",
            password_salt=salt,
            password_hash=pw_hash,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"[BOOTSTRAP] Owner created: {user.phone}")
    finally:
        db.close()


app.include_router(users_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
app.include_router(crm_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(campaigns_router, prefix="/api")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(admin_campaigns_router)
app.include_router(accounts_router, prefix="/api")
app.include_router(admin_accounts_router)
app.include_router(videos_router, prefix="/api")
app.include_router(admin_videos_router)
app.include_router(whatsapp_router, prefix="/api")
app.include_router(admin_whatsapp_router)
app.include_router(superadmin_router)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root(request: Request):
    if request.session.get("uid"):
        return RedirectResponse("/admin", status_code=302)
    return RedirectResponse("/auth", status_code=302)