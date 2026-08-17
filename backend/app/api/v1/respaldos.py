"""Respaldos — respaldos_ejecuciones (bitácora digital §24).

Autenticación separada por endpoint:
  GET  /ejecuciones, /resumen  -> JWT de humano (get_current_user)
  POST /ejecuciones            -> API key de AGENTE (verify_agent_key, §8)
                                  Es el endpoint de ingesta del Agente 3.8/6.5.
"""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.deps_agent import verify_agent_key
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import CatAgente, CatBaseDatos, CatGrupoRespaldo, RespaldoEjecucion
from app.schemas.operacion import RespaldoEjecucionCreate, RespaldoEjecucionOut
from app.services import alertas_service
from app.services.incidencias_service import crear_o_reutilizar_incidencia_sistema

logger = get_logger(__name__)

router = APIRouter(prefix="/respaldos", tags=["respaldos"])


@router.get("/ejecuciones", response_model=list[RespaldoEjecucionOut], dependencies=[Depends(get_current_user)])
def listar_ejecuciones(
    fecha: date | None = None,
    base_datos_id: int | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
) -> list[RespaldoEjecucionOut]:
    stmt = select(RespaldoEjecucion).order_by(RespaldoEjecucion.fecha_ejecucion.desc())
    if fecha is not None:
        stmt = stmt.where(RespaldoEjecucion.fecha_ejecucion == fecha)
    if base_datos_id is not None:
        stmt = stmt.where(RespaldoEjecucion.base_datos_id == base_datos_id)
    if estado is not None:
        stmt = stmt.where(RespaldoEjecucion.estado == estado)
    return [RespaldoEjecucionOut.model_validate(e) for e in db.scalars(stmt).all()]


@router.get("/resumen", dependencies=[Depends(get_current_user)])
def resumen_diario(fecha: date, db: Session = Depends(get_db)) -> dict:
    """Resumen por grupo para la bitácora (§24): {grupo: {total, ok, error}}."""
    rows = db.execute(
        select(
            CatGrupoRespaldo.codigo,
            func.count().label("total"),
            func.sum(func.iif(RespaldoEjecucion.estado == "OK", 1, 0)).label("ok"),
            func.sum(func.iif(RespaldoEjecucion.estado == "ERROR", 1, 0)).label("error"),
        )
        .join(CatBaseDatos, CatBaseDatos.base_datos_id == RespaldoEjecucion.base_datos_id)
        .join(CatGrupoRespaldo, CatGrupoRespaldo.grupo_respaldo_id == CatBaseDatos.grupo_respaldo_id)
        .where(RespaldoEjecucion.fecha_ejecucion == fecha)
        .group_by(CatGrupoRespaldo.codigo)
    ).all()

    return {
        "fecha": fecha.isoformat(),
        "grupos": [
            {"codigo": r.codigo, "total": int(r.total), "ok": int(r.ok or 0), "error": int(r.error or 0)}
            for r in rows
        ],
    }


@router.post("/ejecuciones", response_model=RespaldoEjecucionOut, status_code=200)
def reportar_ejecucion(
    body: RespaldoEjecucionCreate,
    background_tasks: BackgroundTasks,
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> RespaldoEjecucionOut:
    """Ingesta del agente (§8): registra la validación diaria por base.

    Idempotente (§35): si ya existe (BaseDatosId, FechaEjecucion), actualiza
    los campos en lugar de duplicar. El UNIQUE de la tabla actúa como barrera
    definitiva ante carreras (dos requests concurrentes): si el INSERT choca,
    se captura IntegrityError y se reaplica como UPDATE.

    Incidencia automática (§26): si el agente reporta Estado=ERROR, el backend
    crea (o reutiliza) la incidencia con DetectadaPor='SISTEMA' y la vincula a
    la ejecución (respaldos_ejecuciones.IncidenciaId). El agente no reporta
    incidencias: solo hechos.
    """
    base = db.get(CatBaseDatos, body.base_datos_id)
    if base is None:
        raise HTTPException(status_code=422, detail=f"BaseDatosId {body.base_datos_id} no existe")

    datos = body.model_dump(exclude={"base_datos_id", "fecha_ejecucion"})
    logger.info(
        "Ingesta de %s: base %s (%s), fecha %s, estado %s",
        agente.nombre,
        body.base_datos_id,
        base.nombre_base,
        body.fecha_ejecucion,
        body.estado,
    )

    def _aplicar(_ejecucion: RespaldoEjecucion) -> None:
        for campo, valor in datos.items():
            setattr(_ejecucion, campo, valor)

    ejecucion = db.scalar(
        select(RespaldoEjecucion).where(
            RespaldoEjecucion.base_datos_id == body.base_datos_id,
            RespaldoEjecucion.fecha_ejecucion == body.fecha_ejecucion,
        )
    )
    if ejecucion is not None:
        _aplicar(ejecucion)
    else:
        ejecucion = RespaldoEjecucion(
            base_datos_id=body.base_datos_id,
            fecha_ejecucion=body.fecha_ejecucion,
            **datos,
        )
        db.add(ejecucion)
        try:
            db.flush()  # transacción abierta: la incidencia y la ejecución se confirman juntas
        except IntegrityError:
            # Carrera: otra request insertó la misma (Base, Fecha) entre el SELECT y el INSERT.
            db.rollback()
            ejecucion = db.scalar(
                select(RespaldoEjecucion).where(
                    RespaldoEjecucion.base_datos_id == body.base_datos_id,
                    RespaldoEjecucion.fecha_ejecucion == body.fecha_ejecucion,
                )
            )
            if ejecucion is None:
                raise
            _aplicar(ejecucion)

    # §26: cada ERROR reportado genera una incidencia automática (idempotente).
    if body.estado == "ERROR":
        incidencia = crear_o_reutilizar_incidencia_sistema(
            db,
            base=base,
            fecha=body.fecha_ejecucion,
            problema=f"Respaldo de {base.nombre_base} en estado ERROR",
            detalle=(
                f"Reportado por {agente.nombre}. Ejecución #{ejecucion.ejecucion_id}, "
                f"archivo: {body.archivo_encontrado or 'sin archivo'}, "
                f"tamaño: {body.tamano_bytes or 'n/d'} bytes, "
                f"fuera de horario: {'sí' if body.fuera_de_horario else 'no'}"
            ),
        )
        ejecucion.incidencia_id = incidencia.incidencia_id

    alerta = None
    if body.estado in ("ERROR", "ADVERTENCIA"):
        alerta = alertas_service.crear_alerta_si_no_existe(
            db,
            body.estado,
            incidencia_id=ejecucion.incidencia_id if body.estado == "ERROR" else None,
            ejecucion_id=ejecucion.ejecucion_id if body.estado == "ADVERTENCIA" else None,
        )
        if alerta is not None:
            alertas_service.preparar_alerta_respaldo(
                alerta,
                ejecucion=ejecucion,
                base=base,
                agente=agente,
            )

    db.commit()
    db.refresh(ejecucion)

    if alerta is not None:
        background_tasks.add_task(alertas_service.enviar_alerta, alerta.alerta_id)

    return RespaldoEjecucionOut.model_validate(ejecucion)
