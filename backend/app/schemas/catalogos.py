"""Schemas de catálogos (roles, usuarios, servidores, grupos, bases)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rol_id: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    activo: bool


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usuario_id: int
    usuario_externo_id: int | None = None
    nombre_completo: str
    correo: str | None = None
    rol_id: int
    activo: bool
    debe_cambiar_password: bool
    # PasswordHash nunca se expone en la API.


class UsuarioCreate(BaseModel):
    usuario_externo_id: int | None = Field(default=None, description="Referencia opcional a SEGURIDAD_PROSUR")
    nombre_completo: str = Field(min_length=3, max_length=120)
    correo: str | None = Field(default=None, max_length=120)
    rol_id: int
    # Límite de 72 caracteres: máximo que soporta bcrypt (bytes) sin error.
    password: str | None = Field(default=None, min_length=8, max_length=72, description="Contraseña en claro; se hashea con bcrypt antes de guardar")
    debe_cambiar_password: bool = Field(default=True)


class ServidorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    servidor_id: int
    nombre: str
    descripcion: str | None = None
    tipo_servidor: str
    es_nas: bool
    es_origen_respaldo: bool
    activo: bool


class ServidorCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=255)
    tipo_servidor: str = Field(pattern="^(AWS|LOCAL|NAS)$")
    es_nas: bool = False
    es_origen_respaldo: bool = False


class GrupoRespaldoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grupo_respaldo_id: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    activo: bool


class BaseDatosOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_datos_id: int
    grupo_respaldo_id: int
    servidor_origen_id: int | None = None
    nombre_base: str
    tipo_fuente: str
    tipo_backup_predeterminado: str
    observaciones: str | None = None
    activo: bool


class BaseDatosCreate(BaseModel):
    grupo_respaldo_id: int
    servidor_origen_id: int | None = None
    nombre_base: str = Field(min_length=1, max_length=120)
    tipo_fuente: str = Field(pattern="^(SQL|MONGO|MICROSIP|MERCALTOS)$")
    tipo_backup_predeterminado: str = Field(pattern="^(FULL|DIFERENCIAL)$")
    observaciones: str | None = Field(default=None, max_length=255)
