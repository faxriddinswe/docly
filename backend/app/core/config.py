from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "Docly"
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://docly_app:docly_app@localhost:5442/docly"  # RLS-subject role
    migration_database_url: str = "postgresql+asyncpg://docly:docly@localhost:5442/docly"  # owner
    redis_url: str = "redis://localhost:6390/0"
    jwt_secret: str = "dev-only-change-me-0000000000000000"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    min_booking_notice_minutes: int = 60
    rate_limit_per_minute: int = 300  # per client IP, all endpoints
    auth_rate_limit_per_minute: int = 20  # per client IP, login/signup
    otp_ip_limit: int = 20  # OTP requests per IP per 10 min
    book_ip_limit: int = 30  # public bookings per IP per 10 min
    cors_origins: str = "http://localhost:3000"
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    otp_sender: str = "fake"  # fake | eskiz
    eskiz_email: str = ""
    eskiz_password: str = ""
    eskiz_from: str = "4546"
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    reminder_24h_tolerance_minutes: int = 60
    reminder_2h_tolerance_minutes: int = 30
    default_timezone: str = "Asia/Tashkent"

    def validate_prod(self) -> None:
        weak = {"dev-only-change-me-0000000000000000", "change-me", ""}
        if self.env == "prod" and self.jwt_secret in weak:
            raise RuntimeError("JWT_SECRET must be set in production")
        if self.env == "prod" and self.otp_sender == "fake":
            raise RuntimeError("OTP_SENDER=fake is not allowed in production (see docs/BLOCKERS.md B1)")
        if self.env == "prod" and ":docly_app@" in self.database_url:
            raise RuntimeError("DATABASE_URL uses the default dev password")


@lru_cache
def get_settings() -> Settings:
    return Settings()
