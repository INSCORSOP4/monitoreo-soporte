"""Incidencias automáticas del sistema (§26) — generadas por la ingesta de agentes.

El agente solo reporta el hecho (POST /respaldos/ejecuciones); el backend decide
cuándo un estado amerita una incidencia, la crea con DetectadaPor='SISTEMA' y la
vincula al responsable del día vigente (§21). El agente no conoce incidencias.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import CatBaseDatos, CatServidor, CatTipoIncidencia, Incidencia, ResponsableDia

logger = get_logger(__name__)

_CODIGO_FALLBACK = "OTRO"


def _tipo_incidencia_por_fuente(db: Session, tipo_fuente: str) -> int:
    """Mapea el TipoFuente de la base (SQL/MONGO/MICROSIP/MERCALTOS) al catálogo.

    Ej.: SQL -> RESPALDO_SQL, MONGO -> RESPALDO_MONGO. Si el código no existe,
    cae a OTRO en lugar de fallar la ingesta.
    """
    return _tipo_incidencia_por_codigo(db, f"RESPALDO_{tipo_fuente}")


def _tipo_incidencia_por_codigo(db: Session, codigo: str) -> int:
    """Resuelve un código de cat_tipos_incidencia; fallback a OTRO si no existe."""
    tipo = db.scalar(select(CatTipoIncidencia).where(CatTipoIncidencia.codigo == codigo))
    if tipo is None:
        logger.warning("Tipo de incidencia %s no existe en catálogo; se usa %s", codigo, _CODIGO_FALLBACK)
        tipo = db.scalar(select(CatTipoIncidencia).where(CatTipoIncidencia.codigo == _CODIGO_FALLBACK))
        if tipo is None:
            raise ValueError("Catálogo cat_tipos_incidencia vacío")
    return tipo.tipo_incidencia_id


def _responsable_dia(db: Session, fecha: date) -> int | None:
    """Responsable del día vigente (§21).

    Si no hay asignación registrada en responsables_dia para la fecha, devuelve
    None: la incidencia se crea igualmente (ResponsableDiaId NULL) y el equipo
    la asigna en la revisión. Nunca bloquea la ingesta.
    """
    responsable = db.scalar(select(ResponsableDia).where(ResponsableDia.fecha == fecha))
    if responsable is None:
        logger.warning(
            "No hay responsable del día registrado para %s — incidencia sin ResponsableDiaId", fecha
        )
        return None
    return responsable.usuario_id


def crear_o_reutilizar_incidencia_sistema(
    db: Session,
    *,
    base: CatBaseDatos,
    fecha: date,
    problema: str,
    detalle: str | None = None,
) -> Incidencia:
    """Crea una incidencia automática o reutiliza la abierta existente.

    Idempotencia (§35): si el agente reenvía el mismo ERROR, se reutiliza la
    incidencia SISTEMA abierta de (base, fecha) en lugar de duplicar. Cuando el
    estado vuelve a OK, la incidencia queda abierta hasta que Soporte registra
    la intervención (§26) — no se cierra automáticamente.

    Nota: la ejecución queda vinculada vía respaldos_ejecuciones.IncidenciaId
    (el llamador lo asigna después con el id devuelto).

    Barrera de idempotencia: los índices únicos filtrados
    UQ_incidencias_SISTEMA_Abierta / _EnProceso garantizan a nivel BD que solo
    exista UNA incidencia abierta por (Base, Fecha, SISTEMA). Si dos requests
    concurrentes intentan crear la misma, el INSERT choca contra el índice y se
    reutiliza la existente (mismo patrón que las ejecuciones).
    """
    def _abierta_existente():
        return db.scalar(
            select(Incidencia).where(
                Incidencia.base_datos_id == base.base_datos_id,
                Incidencia.fecha_incidencia == fecha,
                Incidencia.detectada_por == "SISTEMA",
                Incidencia.estado.in_(["ABIERTA", "EN_PROCESO"]),
            )
        )

    existente = _abierta_existente()
    if existente is not None:
        return existente

    incidencia = Incidencia(
        tipo_incidencia_id=_tipo_incidencia_por_fuente(db, base.tipo_fuente),
        servidor_id=base.servidor_origen_id,
        base_datos_id=base.base_datos_id,
        fecha_incidencia=fecha,
        estado="ABIERTA",
        detectada_por="SISTEMA",
        problema=problema[:500],
        detalle=detalle,
        responsable_dia_id=_responsable_dia(db, fecha),
    )

    try:
        # SAVEPOINT: si el INSERT choca contra el UNIQUE filtrado (carrera), solo
        # revierte el savepoint, no la transacción externa de la ejecución.
        with db.begin_nested():
            db.add(incidencia)
    except IntegrityError:
        # Otra request creó la incidencia abierta entre el SELECT y el INSERT.
        existente = _abierta_existente()
        if existente is None:
            raise  # no fue la carrera esperada; que lo vea el handler global
        return existente

    logger.info(
        "Incidencia #%s (SISTEMA) creada: base %s, fecha %s, responsable_dia_id %s",
        incidencia.incidencia_id,
        base.nombre_base,
        fecha,
        incidencia.responsable_dia_id,
    )
    return incidencia


def crear_o_reutilizar_incidencia_disco(
    db: Session,
    *,
    servidor: CatServidor,
    fecha: date,
    problema: str,
    detalle: str | None = None,
) -> Incidencia:
    """Incidencia automática del Disco Checker (§26/§33) — una por (servidor, fecha).

    A diferencia de la de respaldos (por base), esta se vincula al SERVIDOR
    (BaseDatosId=NULL) con TipoIncidenciaId=DISCO_SERVIDOR. Idempotente: si el
    checker reenvía el ERROR el mismo día, se reutiliza la incidencia SISTEMA
    abierta (barrera BD: UQ_incidencias_DISCO_Abierta/_EnProceso).
    """
    def _abierta_existente():
        return db.scalar(
            select(Incidencia).where(
                Incidencia.servidor_id == servidor.servidor_id,
                Incidencia.base_datos_id.is_(None),
                Incidencia.fecha_incidencia == fecha,
                Incidencia.detectada_por == "SISTEMA",
                Incidencia.estado.in_(["ABIERTA", "EN_PROCESO"]),
            )
        )

    existente = _abierta_existente()
    if existente is not None:
        return existente

    incidencia = Incidencia(
        tipo_incidencia_id=_tipo_incidencia_por_codigo(db, "DISCO_SERVIDOR"),
        servidor_id=servidor.servidor_id,
        base_datos_id=None,
        fecha_incidencia=fecha,
        estado="ABIERTA",
        detectada_por="SISTEMA",
        problema=problema[:500],
        detalle=detalle,
        responsable_dia_id=_responsable_dia(db, fecha),
    )

    try:
        with db.begin_nested():
            db.add(incidencia)
    except IntegrityError:
        existente = _abierta_existente()
        if existente is None:
            raise
        return existente

    logger.info(
        "Incidencia #%s (SISTEMA/disco) creada: servidor %s, fecha %s, responsable_dia_id %s",
        incidencia.incidencia_id,
        servidor.nombre,
        fecha,
        incidencia.responsable_dia_id,
    )
    return incidencia
