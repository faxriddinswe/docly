from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "Docly"
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://docly:docly@localhost:5442/docly"
    redis_url: str = "redis://localhost:6390/0"
    jwt_secret: str = "dev-only-change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    min_booking_notice_minutes: int = 60
    default_timezone: str = "Asia/Tashkent"


@lru_cache
def get_settings() -> Settings:
    return Settings()
