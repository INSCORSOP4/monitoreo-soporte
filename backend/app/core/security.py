"""Seguridad: tokens JWT y hashing de contraseñas (bcrypt).

- Los usuarios se crean localmente en MONITOREO_SOPORTE y su contraseña se
  almacena SOLO como hash bcrypt (PasswordHash).
- La emisión/validación del token de sesión se gestiona aquí.
"""
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# --- Hashing de contraseñas (bcrypt) ---

def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en claro."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verifica una contraseña en claro contra su hash bcrypt."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# --- API keys de agentes (§8) ---

def generate_api_key() -> str:
    """Genera una API key aleatoria para un agente (se muestra UNA sola vez)."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash bcrypt de la API key (nunca se almacena en claro)."""
    return hash_password(api_key)


def verify_api_key(api_key: str, api_key_hash: str | None) -> bool:
    """Verifica una API key contra su hash bcrypt."""
    return verify_password(api_key, api_key_hash)


# --- Tokens JWT ---

def create_access_token(subject: str, extra_claims: dict | None = None) -> str:
    """Genera un token JWT firmado."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Valida y decodifica un token JWT. Lanza JWTError si es inválido/vencido."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
