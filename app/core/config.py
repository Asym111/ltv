from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SQLite по умолчанию. Потом заменим на PostgreSQL.
    DATABASE_URL: str = "sqlite:///./ltv.db"

    # --- Loyalty / Bonus rules (MVP) ---
    BONUS_PERCENT_BRONZE: float = 3.0
    BONUS_PERCENT_SILVER: float = 5.0
    BONUS_PERCENT_GOLD: float = 7.0

    TIER_SILVER_FROM: float = 500_000
    TIER_GOLD_FROM: float = 2_000_000

    BONUS_ACTIVATION_DAYS: int = 0
    BONUS_BURN_DAYS: int = 60

    REDEEM_MAX_PERCENT: float = 30.0

    BDAY_BONUS_AMOUNT: float = 10_000.0
    BDAY_BONUS_BURN_DAYS: int = 14
    BDAY_MESSAGE_TEMPLATE: str = (
        "С Днём рождения, {name}! Мы начислили вам {amount} бонусов. "
        "Используйте их до {expires_at}."
    )

    # --- AI Providers ---
    # Gemini
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # OpenAI
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"  # можно поменять в .env

    # auto = сначала OpenAI, потом Gemini, потом heuristic (если разрешено)
    AI_PROVIDER: str = "auto"  # auto | openai | gemini | off
    AI_MOCK_IF_NO_KEY: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# --- Backward-compatible module vars (если где-то импортировали напрямую) ---
GEMINI_API_KEY: str | None = settings.GEMINI_API_KEY
GEMINI_MODEL: str = settings.GEMINI_MODEL
OPENAI_API_KEY: str | None = settings.OPENAI_API_KEY
OPENAI_MODEL: str = settings.OPENAI_MODEL
AI_PROVIDER: str = settings.AI_PROVIDER
AI_MOCK_IF_NO_KEY: bool = settings.AI_MOCK_IF_NO_KEY
