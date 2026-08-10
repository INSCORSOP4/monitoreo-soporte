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
from app.models import CatRol, CatUsuario

logger = get_logger(__name__)


class AuthenticationError(Exception):
    """Credenciales inválidas o modo no configurado."""


def authenticate(correo: str, password: str) -> dict:
    """Valida credenciales (login por Correo) y devuelve datos del usuario autenticado."""
    if settings.auth_mode == "stub":
        return _authenticate_stub(correo, password)
    if settings.auth_mode == "seguridad":
        return _authenticate_local(correo, password)
    raise AuthenticationError(f"Modo de autenticación no soportado: {settings.auth_mode}")


def _authenticate_stub(correo: str, password: str) -> dict:
    """Modo desarrollo. Solo debe usarse en local, nunca en producción."""
    if not settings.is_production and correo == "admin" and password == "admin":
        return {"usuario": "admin", "nombre": "Admin de desarrollo", "rol": "ADMINISTRADOR"}
    raise AuthenticationError("Credenciales inválidas")


def _authenticate_local(correo: str, password: str) -> dict:
    """Valida contra MONITOREO_SOPORTE.dbo.cat_usuarios (hash bcrypt local)."""
    with SessionLocal() as db:
        # El Correo es el identificador real de login (único y obligatorio, UQ_cat_usuarios_Correo).
        # NOTA: en SQL Server debe usarse `== True` (genera `= 1`); `.is_(True)`
        # generaría `IS 1`, sintaxis inválida en este motor.
        cat_usuario = db.scalar(
            select(CatUsuario).where(CatUsuario.correo == correo, CatUsuario.activo == True)  # noqa: E712
        )
        if cat_usuario is None or not verify_password(password, cat_usuario.password_hash):
            raise AuthenticationError("Credenciales inválidas")
        # Resuelve el rol real desde cat_roles (§22)
        rol = db.get(CatRol, cat_usuario.rol_id)
        return {
            "usuario": cat_usuario.correo,
            "nombre": cat_usuario.nombre_completo,
            "rol": rol.codigo if rol else "SOPORTE",
            "usuario_id": cat_usuario.usuario_id,
            "debe_cambiar_password": cat_usuario.debe_cambiar_password,
        }
