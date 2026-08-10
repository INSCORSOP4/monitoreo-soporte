"""Schemas de operación (ejecuciones, incidencias, alertas, historial)."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RespaldoEjecucionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ejecucion_id: int
    base_datos_id: int
    fecha_ejecucion: date
    estado: str
    tipo_backup_encontrado: str | None = None
    archivo_encontrado: str | None = None
    tamano_bytes: int | None = None
    fecha_generacion: datetime | None = None
    fuera_de_horario: bool | None = None
    detalle: str | None = None


class IncidenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incidencia_id: int
    tipo_incidencia_id: int
    servidor_id: int | None = None
    base_datos_id: int | None = None
    fecha_incidencia: date
    estado: str
    detectada_por: str
    problema: str
    detalle: str | None = None
    resultado: str | None = None
    fecha_resolucion: datetime | None = None


class IncidenciaCreate(BaseModel):
    tipo_incidencia_id: int
    servidor_id: int | None = None
    base_datos_id: int | None = None
    fecha_incidencia: date
    problema: str = Field(min_length=5, max_length=500)
    detalle: str | None = None


class AccionIncidenciaCreate(BaseModel):
    usuario_id: int
    descripcion: str = Field(min_length=3)
    resultado: str | None = Field(default=None, pattern="^(CORRECTO|INCORRECTO|EN_PROCESO)$")


class AlertaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alerta_id: int
    incidencia_id: int | None = None
    tipo_evento: str
    asunto: str
    estado: str
    fecha_envio: datetime | None = None


class HistorialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    historial_id: int
    fecha_evento: datetime
    usuario_id: int | None = None
    entidad: str
    entidad_id: int | None = None
    tipo_evento: str
    descripcion: str | None = None
