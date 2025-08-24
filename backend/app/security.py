import secrets
import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from .config import get_settings

ph = PasswordHasher()

def hash_password(plain: str) -> str:
    return ph.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False

def create_access_token(sub: int, email: str, name: str | None, roles: list[str]) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(sub),
        "email": email,
        "name": name or "",
        "roles": roles,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "quality.local",
        "aud": "quality.api"
    }
    return jwt.encode(payload, settings.APP_SECRET, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.APP_SECRET,
        algorithms=["HS256"],
        audience="quality.api",
        options={"require": ["exp", "iat", "sub", "type"]}
    )

def new_refresh_token() -> str:
    # token opaco aleatorio
    return secrets.token_urlsafe(64)

def hash_token(token: str) -> str:
    # guardamos solo hash del refresh token
    h = hashlib.sha256()
    h.update(token.encode("utf-8"))
    return h.hexdigest()

def refresh_token_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)