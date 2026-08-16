"""Responsable del día (§21) — asignación automática por rotación.

La rotación recorre `rotacion` por Orden (1, 2, 3...) saltando participantes no
activos, y da la vuelta al llegar al final. La última asignación AUTO registrada
en `responsables_dia` (la más reciente por fecha, sin importar si fue día hábil
consecutivo) indica dónde va el ciclo: se asigna el siguiente Orden activo.

Si nunca hubo asignación previa, se empieza en Orden=1 (el primer participante
activo). Una asignación MANUAL del coordinador para una fecha se respeta tal
cual — la rotación solo calcula cuando no hay fila para esa fecha.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import CatUsuario, ResponsableDia, Rotacion

logger = get_logger(__name__)


def _participantes_activos(db: Session) -> list:
    """Participantes del ciclo ordenados por Orden, solo los activos.

    'Activo en el ciclo' = no suspendido en la rotación (Suspendido=0) Y usuario
    activo en cat_usuarios (Activo=1). Un usuario dado de baja o suspendido
    temporalmente se salta sin romper la secuencia.
    """
    return db.execute(
        select(Rotacion, CatUsuario)
        .join(CatUsuario, CatUsuario.usuario_id == Rotacion.usuario_id)
        .where(
            Rotacion.suspendido == False,  # noqa: E712  (SQL Server: = 0)
            CatUsuario.activo == True,  # noqa: E712  (SQL Server: = 1)
        )
        .order_by(Rotacion.orden)
    ).all()


def _siguiente_rotacion(db: Session, fecha: date) -> int | None:
    """UsuarioId del siguiente participante del ciclo, o None si no hay ninguno.

    Se toma la última asignación AUTO de responsables_dia ANTERIOR a la fecha
    (la más reciente; no importa si fue día hábil consecutivo) y se avanza a su
    siguiente Orden activo; al llegar al final se vuelve al primer activo. Si el
    último AUTO ya no está en la rotación (fue removido) o nunca hubo asignación
    previa, se empieza en el Orden=1 activo.
    """
    activos = _participantes_activos(db)
    if not activos:
        logger.warning("No hay participantes activos en rotacion — sin responsable del día")
        return None

    ultima = db.scalar(
        select(ResponsableDia)
        .where(
            ResponsableDia.origen_asignacion == "AUTO",
            ResponsableDia.fecha < fecha,
        )
        .order_by(ResponsableDia.fecha.desc())
        .limit(1)
    )
    if ultima is None:
        return activos[0].Rotacion.usuario_id  # nunca hubo previa: Orden=1 activo

    fila_ultima = db.scalar(select(Rotacion).where(Rotacion.usuario_id == ultima.usuario_id))
    if fila_ultima is None:
        # El último asignado ya no participa del ciclo: empezar de nuevo.
        return activos[0].Rotacion.usuario_id

    for rotacion, _usuario in activos:
        if rotacion.orden > fila_ultima.orden:
            return rotacion.usuario_id

    # Se llegó al final del ciclo: dar la vuelta al primer activo.
    return activos[0].Rotacion.usuario_id


def obtener_o_crear_responsable_dia(db: Session, fecha: date) -> int | None:
    """UsuarioId del responsable de la fecha, creando la asignación AUTO si falta.

    La asignación automática solo aplica en DÍAS HÁBILES (lun-vie): si la fecha
    cae en fin de semana (sáb=5, dom=6) no se intenta la rotación y se devuelve
    None — la incidencia queda sin ResponsableDiaId y el log registra el aviso.
    En día hábil:
    - Si ya hay fila en responsables_dia para la fecha (AUTO o MANUAL), se
      respeta y devuelve su UsuarioId.
    - Si no hay, calcula el siguiente del ciclo por rotación y registra la
      asignación con OrigenAsignacion='AUTO' (idempotente por UNIQUE(Fecha);
      ante una carrera con otra request se reutiliza la fila existente).
    - Si no hay participantes activos, devuelve None: la incidencia se crea
      igualmente (ResponsableDiaId NULL) y queda para la revisión.
    """
    if fecha.weekday() >= 5:
        logger.warning(
            "Fecha %s en fin de semana — no se asigna responsable automático (NULL)",
            fecha,
        )
        return None

    existente = db.scalar(select(ResponsableDia).where(ResponsableDia.fecha == fecha))
    if existente is not None:
        return existente.usuario_id

    usuario_id = _siguiente_rotacion(db, fecha)
    if usuario_id is None:
        return None

    asignacion = ResponsableDia(
        fecha=fecha,
        usuario_id=usuario_id,
        origen_asignacion="AUTO",
    )
    try:
        # SAVEPOINT: si otra request insertó la misma fecha entre el SELECT y el
        # INSERT (UNIQUE Fecha), solo se revierte el savepoint, no la transacción.
        with db.begin_nested():
            db.add(asignacion)
    except IntegrityError:
        existente = db.scalar(select(ResponsableDia).where(ResponsableDia.fecha == fecha))
        if existente is None:
            raise
        return existente.usuario_id

    logger.info(
        "Responsable del día %s (AUTO/rotación): usuario %s",
        fecha, usuario_id,
    )
    return usuario_id
