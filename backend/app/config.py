from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # --- DB ---
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str

    # --- Auth genérico ---
    AUTH_PROVIDER: str = "local"          # "local" o "azure"
    AUTH_DISABLED: bool = False           # si True, usa "Dev User"
    APP_SECRET: Optional[str] = None      # requerido si AUTH_PROVIDER=local (HS256)

    # Identificadores del API (coinciden con el JWT emitido)
    API_AUDIENCE: str = "quality.api"
    API_ISSUER: str = "quality.local"

    # Azure (opcional, para si vuelves a usarlo)
    TENANT_ID: Optional[str] = None
    CLIENT_ID: Optional[str] = None
    JWKS_CACHE_SECONDS: int = 3600

    # Roles permitidos (por si necesitas validar listas)
    ALLOWED_ROLES: str = "Admin,User"

    # Cookies / tiempos tokens
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_DOMAIN: str = "127.0.0.1"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_PATH: str = "/auth"   # <— NUEVO (default dev)

    # Bootstrap del primer admin
    BOOTSTRAP_TOKEN: Optional[str] = None

    class Config:
        env_file = ".env"

    @property
    def database_url(self):
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

@lru_cache
def get_settings():
    return Settings()