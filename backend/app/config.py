from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Headline Avenue API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./headline_avenue.db"
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5500,"
        "https://headlineavenue.github.io"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
