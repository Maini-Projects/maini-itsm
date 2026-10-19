"""Settings, read from environment variables (or a local .env file)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres connection string (Supabase: Project Settings > Database > Connection string)
    database_url: str
    db_pool_max: int = 5

    # Supabase Auth: used to verify login tokens and to create users
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Supabase Storage bucket for attached files (created by migration 005; private)
    attachments_bucket: str = "attachments"

    # Comma-separated list of front-end addresses allowed to call the API from a browser
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # How long a verified login token is trusted before Supabase is asked again
    token_cache_seconds: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
