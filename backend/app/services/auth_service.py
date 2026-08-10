"""Servicio de autenticación.

AUTH_MODE=stub       -> desarrollo: usuario "admin"/"admin" (solo local, nunca producción).
AUTH_MODE=seguridad  -> producción: valida contra MONITOREO_SOPORTE.dbo.cat_usuarios
                        (usuarios locales creados con POST /usuarios, hash bcrypt).

La contraseña NUNCA se almacena en claro: solo el hash bcrypt en PasswordHash.
"""
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.core.security import verify_password
from app.models import CatUsuario

logger = get_logger(__name__)


class AuthenticationError(Exception):
    """Credenciales inválidas o modo no configurado."""


def authenticate(usuario: str, password: str) -> dict:
    """Valida credenciales y devuelve datos del usuario autenticado."""
    if settings.auth_mode == "stub":
        return _authenticate_stub(usuario, password)
    if settings.auth_mode == "seguridad":
        return _authenticate_local(usuario, password)
    raise AuthenticationError(f"Modo de autenticación no soportado: {settings.auth_mode}")


def _authenticate_stub(usuario: str, password: str) -> dict:
    """Modo desarrollo. Solo debe usarse en local, nunca en producción."""
    if not settings.is_production and usuario == "admin" and password == "admin":
        return {"usuario": "admin", "nombre": "Admin de desarrollo", "rol": "ADMINISTRADOR"}
    raise AuthenticationError("Credenciales inválidas")


def _authenticate_local(usuario: str, password: str) -> dict:
    """Valida contra MONITOREO_SOPORTE.dbo.cat_usuarios (hash bcrypt local)."""
    with SessionLocal() as db:
        # TODO: el esquema aún no tiene columna de login; se autentica por nombre_completo
        # hasta definir el flujo real de usuario/contraseña local.
        cat_usuario = db.scalar(
            select(CatUsuario).where(CatUsuario.nombre_completo == usuario, CatUsuario.activo.is_(True))
        )
        if cat_usuario is None or not verify_password(password, cat_usuario.password_hash):
            raise AuthenticationError("Credenciales inválidas")
        rol = "SOPORTE"  # TODO(Fase 3): resolver el rol desde cat_roles por rol_id
        return {
            "usuario": cat_usuario.nombre_completo,
            "nombre": cat_usuario.nombre_completo,
            "rol": rol,
            "usuario_id": cat_usuario.usuario_id,
            "debe_cambiar_password": cat_usuario.debe_cambiar_password,
        }
