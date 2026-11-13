from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Headline Avenue API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./headline_avenue.db"
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5500,"
        "https://headlineavenue.github.io,https://headlineavenue.com,"
        "https://www.headlineavenue.com"
    )
    frontend_origin: str = "http://localhost:5500"

    auth_cookie_name: str = "ha_session"
    auth_session_days: int = 30
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_registration_enabled: bool = True
    auth_bootstrap_owner_email: str = ""
    auth_bootstrap_owner_password: str = ""
    auth_bootstrap_owner_name: str = "Headline Avenue Owner"
    token_encryption_key: str = ""

    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = ""
    tiktok_scopes: str = "user.info.basic"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        return self.auth_cookie_secure or self.app_env.lower() == "production"

    @property
    def session_cookie_samesite(self) -> str:
        value = self.auth_cookie_samesite.strip().lower()
        if value not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        if value == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
