"""Schemas de agentes (máquinas, §8)."""
from pydantic import BaseModel, ConfigDict, Field


class AgenteCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$", description="Ej.: AGENTE_10.0.3.8")
    activo: bool = True


class AgenteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agente_id: int
    nombre: str
    activo: bool
    # ApiKeyHash nunca se expone en la API.


class AgenteWithApiKey(BaseModel):
    """Respuesta de creación: incluye la API key en claro (única vez)."""

    agente_id: int
    nombre: str
    activo: bool
    api_key: str
