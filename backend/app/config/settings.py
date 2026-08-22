from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "NekoSalesAI"
    APP_VERSION: str = "1.0.0"

    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./nekosales.db"

    # Signing key for access tokens. The default is a known, published
    # string — safe for local development, catastrophic in production, so
    # main.py warns loudly at startup while it is still in place.
    SECRET_KEY: str = "dev-only-insecure-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Comma-separated list of allowed browser origins for the web app.
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # The organization whose product the public storefront sells. This
    # deployment sells NekoSalesAI itself, so the landing page and public
    # chat widget both resolve to this one org.
    STOREFRONT_ORG_SLUG: str = "nekosales-demo"

    # The seeded demo login. Both defaults are published in this repo, so the
    # password has to be overridable before the app is reachable from outside
    # the machine it runs on — the desk it opens holds buyer conversations,
    # contact details and the approval queue.
    DEMO_USER_EMAIL: str = "founder@nekosales.ai"
    DEMO_USER_PASSWORD: str = "demo-password-2026"

    # Public base URL, used to build the callback Paystack sends the buyer
    # back to after checkout. Must be the address the browser can reach,
    # not the address the server binds to.
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    # Paystack credentials. Empty by default and deliberately so: an unset
    # key disables checkout and says why, which is a better failure than a
    # payment button that 500s. Use the sk_test_/pk_test_ pair until live
    # payments are actually intended.
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"

    # Email. The default backend logs instead of sending, which is deliberate:
    # a fresh clone runs the whole purchase flow and shows what would have gone
    # out, and no test can accidentally mail a real person. Set "smtp" and the
    # credentials below to send for real.
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

    # Groq, for rephrasing the deterministic agent's replies. Empty by default
    # and the feature stays off — the rule engine composes every reply on its
    # own, and the model may only change wording. See app.sales.rephrase for
    # what it is structurally prevented from doing.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    # Short on purpose. A visitor waiting on a chat reply will not wait, so a
    # slow model is dropped and the deterministic text ships instead.
    LLM_TIMEOUT_SECONDS: float = 3.5

    # Telegram. Empty disables the channel: a follow-up preference naming it is
    # skipped with a reason rather than failing, and the webhook returns 503.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BASE_URL: str = "https://api.telegram.org"
    # Shared secret echoed by Telegram in X-Telegram-Bot-Api-Secret-Token. The
    # webhook must be public, so without this anyone who learns the URL could
    # post fabricated messages into a customer's conversation.
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # WhatsApp, via the Meta Cloud API. Needs both the token and the phone
    # number id; either missing disables the channel.
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BASE_URL: str = "https://graph.facebook.com/v21.0"
    # Echoed back during Meta's webhook handshake.
    WHATSAPP_VERIFY_TOKEN: str = ""
    # Meta signs every delivery with this. Used to verify X-Hub-Signature-256.
    WHATSAPP_APP_SECRET: str = ""

    MESSAGING_TIMEOUT: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
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
        """True only for a live secret key.

        Worth knowing at a glance: it drives the startup banner, so nobody
        discovers they were charging real cards by finding a real charge.
        """
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
