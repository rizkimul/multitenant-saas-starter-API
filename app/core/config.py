from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Stripe
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_id: str  # default plan price ID

    # Rate limiting (per workspace, fixed window)
    rate_limit_requests: int = 60   # max requests per window
    rate_limit_window_seconds: int = 60  # window size in seconds

    # App
    debug: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Assemble the async-compatible PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance.

    Returns:
        Settings: Validated settings loaded from environment / .env file.
    """
    return Settings()  # type: ignore[call-arg]
