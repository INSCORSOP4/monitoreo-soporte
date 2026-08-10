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
#
# Formato: '<AgenteId>.<secreto>'   (ej.: "3.SxK9f...")
#   - AgenteId: ruta de búsqueda directa por PK (no es un secreto; es un INT
#     secuencial visible en GET /agentes). Permite al middleware hacer UN SOLO
#     lookup y UN SOLO bcrypt en vez de probar contra todos los agentes (O(n)).
#   - secreto: 43 chars aleatorios. Es lo único secreto y lo único que se
#     persiste hasheado (ApiKeyHash = bcrypt(secreto)).
#
# Esto elimina de raíz el riesgo de DoS por costo de bcrypt: las keys con
# formato inválido o con AgenteId inexistente se rechazan SIN tocar bcrypt.

def generate_secreto() -> str:
    """Secreto aleatorio de la API key (43 chars URL-safe)."""
    return secrets.token_urlsafe(32)


def compose_api_key(agente_id: int, secreto: str) -> str:
    """Compone la key pública '<AgenteId>.<secreto>' (se muestra UNA sola vez)."""
    return f"{agente_id}.{secreto}"


def parse_api_key(api_key: str) -> tuple[int, str] | None:
    """Separa '<AgenteId>.<secreto>'. Devuelve None si el formato es inválido.

    El AgenteId debe ser un entero positivo y el secreto no vacío con al menos
    16 chars (las keys generadas tienen 43; el mínimo es defensa en profundidad
    contra keys débiles hipotéticas).
    """
    if not api_key:
        return None
    partes = api_key.split(".")
    if len(partes) != 2 or not partes[0].isdigit() or len(partes[1]) < 16:
        return None
    agente_id = int(partes[0])
    if agente_id <= 0:
        return None
    return agente_id, partes[1]


def hash_api_key(secreto: str) -> str:
    """Hash bcrypt del SECRETO de la key (el AgenteId no es secreto, no se hashea)."""
    return hash_password(secreto)


def verify_api_key(secreto: str, api_key_hash: str | None) -> bool:
    """Verifica el secreto de la key contra su hash bcrypt."""
    return verify_password(secreto, api_key_hash)


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
