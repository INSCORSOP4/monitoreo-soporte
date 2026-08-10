"""Dependencias compartidas de la API."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_access_token

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Valida el token JWT y devuelve el usuario autenticado.

    En AUTH_MODE=stub (desarrollo) se permite el acceso sin token
    (útil para probar la API sin autenticación).
    En AUTH_MODE=seguridad (producción) el token es obligatorio.
    """
    if credentials is None:
        if settings.auth_mode == "stub":
            logger.debug("Acceso sin token en modo stub (desarrollo)")
            return {"usuario": "admin", "rol": "ADMINISTRADOR"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        ) from exc

    usuario = payload.get("sub")
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin usuario",
        )
    return {"usuario": usuario, **payload.get("extra", {})}
