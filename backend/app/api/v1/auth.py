"""Autenticación — login JWT y perfil del usuario actual (§22)."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth_service import AuthenticationError, authenticate

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    try:
        # El login busca al usuario por Correo (identificador único, §22)
        usuario = authenticate(body.correo, body.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    token = create_access_token(
        subject=usuario["usuario"],
        extra_claims={"extra": {"nombre": usuario.get("nombre"), "rol": usuario.get("rol")}},
    )
    logger.info("Login exitoso: %s", usuario["usuario"])
    return LoginResponse(
        access_token=token,
        expires_minutes=settings.jwt_expire_minutes,
        usuario=usuario["usuario"],
        nombre=usuario.get("nombre"),
        rol=usuario.get("rol"),
        debe_cambiar_password=bool(usuario.get("debe_cambiar_password")),
    )
