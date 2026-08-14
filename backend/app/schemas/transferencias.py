"""Schemas de transferencias SQL -> NAS (§11, §30).

La transferencia es el movimiento de un respaldo YA validado (Estado=OK en
respaldos_ejecuciones) hacia la ruta destino del NAS. La regla crítica §30:
`OrigenEliminado` solo puede registrarse en 1 cuando la transferencia quedó
COMPLETADA con la validación aprobada (hash coincidente, o hash no solicitado
— HASH_VALIDACION=false — con tamaño/fecha confirmados). Nunca copiar->eliminar.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ESTADOS_TRANSFERENCIA = Literal["EN_PROGRESO", "COMPLETADA", "FALLIDA", "PENDIENTE"]


class TransferenciaExistenteOut(BaseModel):
    """Transferencia previa no COMPLETADA (para calcular RetryNumber)."""

    transferencia_id: int
    estado: str
    retry_number: int


class PendienteTransferirItem(BaseModel):
    """Una ejecución OK pendiente: transferir al NAS, o terminar el borrado.

    - solo_eliminar=False: sin transferencia COMPLETADA -> flujo §11 completo.
    - solo_eliminar=True: COMPLETADA con OrigenEliminado=0 de una corrida previa
      -> el worker reintenta SOLO la eliminación (§30 recuperación), sin re-copiar.
    """

    ejecucion_id: int
    base_datos_id: int
    nombre_base: str
    grupo_codigo: str | None = None
    archivo_encontrado: str
    tamano_bytes: int | None = None
    fecha_generacion: str | None = None
    ruta_origen: str
    ruta_destino: str
    eliminar_origen_tras_transferencia: bool = True
    solo_eliminar: bool = False
    transferencia_existente: TransferenciaExistenteOut | None = None


class PendientesTransferirOut(BaseModel):
    fecha: str
    agente_id: int
    agente_nombre: str
    items: list[PendienteTransferirItem] = []


class TransferenciaCreate(BaseModel):
    """Reporte del NAS Transfer Worker (POST /transferencias, X-Agent-Key)."""

    ejecucion_id: int
    base_datos_id: int
    estado: ESTADOS_TRANSFERENCIA
    ruta_origen_efectiva: str = Field(max_length=500)
    ruta_destino_efectiva: str = Field(max_length=500)
    tamano_origen_bytes: int | None = None
    tamano_destino_bytes: int | None = None
    hash_origen: str | None = Field(default=None, max_length=64)
    hash_destino: str | None = Field(default=None, max_length=64)
    hash_coincide: bool | None = None
    origen_eliminado: bool = False
    error_detalle: str | None = Field(default=None, max_length=4000)
    retry_number: int = Field(default=1, ge=1, le=255)


class TransferenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transferencia_id: int
    ejecucion_id: int
    base_datos_id: int
    fecha_transferencia: datetime
    retry_number: int
    estado: str
    ruta_origen_efectiva: str
    ruta_destino_efectiva: str
    tamano_origen_bytes: int | None
    tamano_destino_bytes: int | None
    hash_origen: str | None
    hash_destino: str | None
    hash_coincide: bool | None
    origen_eliminado: bool
    error_detalle: str | None
    incidencia_id: int | None
