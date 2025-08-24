# app/auth.py
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from cachetools import TTLCache
from jwt import PyJWKClient
import jwt
import requests

from .config import get_settings

settings = get_settings()
bearer = HTTPBearer(auto_error=True)

# Cache sólo usado si provider=azure
_jwks_cache = TTLCache(maxsize=2, ttl=get_settings().JWKS_CACHE_SECONDS)

def _jwks_uri():
    oidc = f"https://login.microsoftonline.com/{settings.TENANT_ID}/v2.0/.well-known/openid-configuration"
    r = requests.get(oidc, timeout=5)
    r.raise_for_status()
    return r.json()["jwks_uri"]

def _get_jwk_client():
    if "jwks_uri" not in _jwks_cache:
        _jwks_cache["jwks_uri"] = _jwks_uri()
    return PyJWKClient(_jwks_cache["jwks_uri"])

def _verify_local(token: str):
    """
    Verifica tokens HS256 emitidos localmente con APP_SECRET.
    Valida issuer (API_ISSUER) y audience (API_AUDIENCE).
    """
    try:
        payload = jwt.decode(
            token,
            settings.APP_SECRET,
            algorithms=["HS256"],
            audience=settings.API_AUDIENCE,
            issuer=settings.API_ISSUER,
        )
        # Normalizar roles a lista
        roles = payload.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        payload["roles"] = roles
        return payload
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

def _verify_azure(token: str):
    """
    Verifica tokens RS256 de Azure AD con JWKS. (Sólo si AUTH_PROVIDER=azure)
    """
    try:
        jwk_client = _get_jwk_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token).key
        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.API_AUDIENCE,
            issuer=f"https://login.microsoftonline.com/{settings.TENANT_ID}/v2.0",
        )
        roles = decoded.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        decoded["roles"] = roles
        return decoded
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

def verify_token(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """
    Decide según AUTH_PROVIDER. Si AUTH_DISABLED=True, devuelve usuario fake Admin (sólo dev).
    """
    if settings.AUTH_DISABLED:
        return {
            "name": "Dev User",
            "preferred_username": "dev@local",
            "roles": ["Admin"],
            "aud": "dev",
            "iss": "dev",
            "sub": "0",
        }

    token = creds.credentials
    provider = (settings.AUTH_PROVIDER or "local").strip().lower()
    if provider == "local":
        return _verify_local(token)
    elif provider == "azure":
        return _verify_azure(token)
    else:
        # fallback seguro
        raise HTTPException(status_code=500, detail="AUTH_PROVIDER inválido. Use 'local' o 'azure'.")

def require_roles(*roles):
    allowed = set(r.strip() for r in roles if r and r.strip())
    def _inner(decoded = Depends(verify_token)):
        if not allowed:
            return decoded
        token_roles = set(decoded.get("roles") or [])
        if token_roles.isdisjoint(allowed):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return decoded
    return _inner