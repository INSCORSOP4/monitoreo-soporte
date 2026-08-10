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
    incidencia_id: int | None = None  # §26: incidencia automática vinculada (si ERROR)


class RespaldoEjecucionCreate(BaseModel):
    """Reporte del agente (§8, §24). Idempotente por (BaseDatosId, FechaEjecucion)."""

    base_datos_id: int = Field(gt=0)
    fecha_ejecucion: date
    estado: str = Field(pattern="^(OK|ADVERTENCIA|ERROR|PENDIENTE|NO_APLICA)$")
    tipo_backup_encontrado: str | None = Field(default=None, pattern="^(FULL|DIFERENCIAL)$")
    archivo_encontrado: str | None = Field(default=None, max_length=500)
    tamano_bytes: int | None = Field(default=None, ge=0)
    fecha_generacion: datetime | None = None
    fuera_de_horario: bool | None = None
    detalle: str | None = Field(default=None, max_length=2000)  # trazabilidad del agente (§35)


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
    responsable_dia_id: int | None = None  # §21: responsable del día
    usuario_atendio_id: int | None = None  # quien intervino (distinto del responsable)
    accion_tomada: str | None = None
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
