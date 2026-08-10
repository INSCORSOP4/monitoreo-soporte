"""Schemas de autenticación (JWT, §22)."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    usuario: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_minutes: int
    usuario: str
    nombre: str | None = None
    rol: str | None = None
    debe_cambiar_password: bool = False
