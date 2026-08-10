"""Schemas de autenticación (JWT, §22)."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # El correo es el identificador de login (único en cat_usuarios)
    correo: str = Field(min_length=3, max_length=120)
    # Límite de 72 caracteres: máximo que soporta bcrypt (bytes) sin error
    password: str = Field(min_length=1, max_length=72)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    usuario: str
    nombre: str | None = None
    rol: str | None = None
    debe_cambiar_password: bool = False
