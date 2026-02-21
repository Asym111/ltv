from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./ltv.db"

    # --- Loyalty / Bonus rules ---
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
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    AI_PROVIDER: str = "auto"
    AI_MOCK_IF_NO_KEY: bool = True

    # --- WhatsApp / GreenAPI ---
    GREENAPI_INSTANCE_ID: str | None = None    # ID инстанса из личного кабинета GreenAPI
    GREENAPI_API_TOKEN: str | None = None      # API токен из личного кабинета GreenAPI
    # Базовый URL (не менять без причины)
    GREENAPI_BASE_URL: str = "https://api.green-api.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# --- Backward-compatible ---
GEMINI_API_KEY: str | None = settings.GEMINI_API_KEY
GEMINI_MODEL: str = settings.GEMINI_MODEL
OPENAI_API_KEY: str | None = settings.OPENAI_API_KEY
OPENAI_MODEL: str = settings.OPENAI_MODEL
AI_PROVIDER: str = settings.AI_PROVIDER
AI_MOCK_IF_NO_KEY: bool = settings.AI_MOCK_IF_NO_KEY