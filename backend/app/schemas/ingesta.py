"""Schemas de ingesta de agentes (§8) — configuración que el agente consume.

El agente NO tiene la configuración quemada: la lee del backend con su
X-Agent-Key (§35). Este endpoint le entrega el catálogo completo de bases
con sus rutas y horarios esperados.
"""
from pydantic import BaseModel, ConfigDict


class HorarioConfigOut(BaseModel):
    dia_semana: int  # 1=Lun ... 7=Dom
    dia_aplica: bool
    tipo_backup_esperado: str  # FULL / DIFERENCIAL
    hora_esperada: str  # "HH:MM"
    tolerancia_minutos: int


class BaseConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_datos_id: int
    grupo_respaldo_id: int
    grupo_codigo: str
    nombre_base: str
    tipo_fuente: str  # SQL / MONGO / MICROSIP / MERCALTOS
    tipo_backup_predeterminado: str
    activo: bool
    ruta_origen: str | None = None
    ruta_destino: str | None = None
    horarios: list[HorarioConfigOut] = []


class ConfiguracionIngestaOut(BaseModel):
    agente_id: int
    agente_nombre: str
    generado_en: str
    bases: list[BaseConfigOut]
