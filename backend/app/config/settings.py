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

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

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
