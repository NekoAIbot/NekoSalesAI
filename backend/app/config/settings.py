from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env path: settings.py is at backend/app/config/settings.py
# .env is at backend/.env
_settings_dir = Path(__file__).resolve().parent
_backend_root = _settings_dir.parent.parent  # config -> app -> backend
_env_path = _backend_root / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "NekoSalesAI"
    APP_VERSION: str = "1.0.0"

    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./nekosales.db"

    SECRET_KEY: str = "dev-only-insecure-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    STOREFRONT_ORG_SLUG: str = "nekosales-demo"

    DEMO_USER_EMAIL: str = "founder@nekosales.ai"
    DEMO_USER_PASSWORD: str = "demo-password-2026"

    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"

    MAIL_BACKEND: str = "console"
    MAIL_FROM: str = "hello@nekosales.ai"
    MAIL_FROM_NAME: str = "NekoSalesAI"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT: int = 20

    BREVO_API_KEY: str = ""

    GROQ_API_KEY: str = ""
    # The current Groq catalog. llama-3.3-70b-versatile was retired; gpt-oss-20b
    # is the fastest chat model available on this key (~1.1s). Override with
    # GROQ_MODEL in .env if the catalog changes again.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_TIMEOUT_SECONDS: float = 3.5
    # The semantic-understanding calls get a longer budget than rephrasing:
    # they run only on the slow path (messages the deterministic engine could
    # not read) and a timeout there falls back to deterministic behaviour
    # rather than degrading the answer.
    LLM_UNDERSTANDING_TIMEOUT_SECONDS: float = 6.0

    # Set by the test suite (tests/conftest.py) so a live GROQ_API_KEY in the
    # developer's .env cannot make the tests non-deterministic.
    TESTING: bool = False

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BASE_URL: str = "https://api.telegram.org"
    TELEGRAM_WEBHOOK_SECRET: str = ""

    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BASE_URL: str = "https://graph.facebook.com/v21.0"
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_APP_ID: str = ""

    MESSAGING_TIMEOUT: float = 10.0

    model_config = SettingsConfigDict(
        env_file=str(_env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def payments_enabled(self) -> bool:
        return bool(self.PAYSTACK_SECRET_KEY.strip())

    @property
    def paystack_is_live(self) -> bool:
        return self.PAYSTACK_SECRET_KEY.strip().startswith("sk_live_")

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
