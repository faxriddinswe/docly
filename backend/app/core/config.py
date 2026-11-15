from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "Docly"
    env: str = "dev"
    database_url: str = (
        "postgresql+asyncpg://docly_app:docly_app@localhost:5442/docly"  # RLS-subject role
    )
    migration_database_url: str = "postgresql+asyncpg://docly:docly@localhost:5442/docly"  # owner
    redis_url: str = "redis://localhost:6390/0"
    jwt_secret: str = "dev-only-change-me-0000000000000000"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    min_booking_notice_minutes: int = 60
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_sender: str = "fake"  # fake | eskiz
    eskiz_email: str = ""
    eskiz_password: str = ""
    eskiz_from: str = "4546"
    default_timezone: str = "Asia/Tashkent"

    def validate_prod(self) -> None:
        weak = {"dev-only-change-me-0000000000000000", "change-me", ""}
        if self.env == "prod" and self.jwt_secret in weak:
            raise RuntimeError("JWT_SECRET must be set in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
