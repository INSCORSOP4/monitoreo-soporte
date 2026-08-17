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


class JobPasoConfigOut(BaseModel):
    paso_monitoreado_id: int
    job_monitoreado_id: int
    nombre_job: str
    step_id: int
    nombre_paso: str
    horarios: list[HorarioConfigOut] = []


class ConfiguracionIngestaOut(BaseModel):
    agente_id: int
    agente_nombre: str
    # Servidor donde corre ESTE agente (cat_agentes.ServidorId, §33). Lo usa el
    # Disco Checker para reportar discos_lecturas con su ServidorId — el agente
    # no lo tiene quemado (§35): lo lee de aquí.
    servidor_id: int | None = None
    generado_en: str
    bases: list[BaseConfigOut]
    jobs_pasos: list[JobPasoConfigOut] = []
    # Disco Checker (§33): umbrales GLOBALES de espacio libre (%). El agente los
    # lee de aquí — no los tiene quemados (§35). Misma política para todas las
    # unidades; si algún día se necesita por unidad, se agrega después.
    disco_warning_pct: int
    disco_error_pct: int
