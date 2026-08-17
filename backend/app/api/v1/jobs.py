"""Ingesta de ejecuciones de pasos de SQL Server Agent."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps_agent import verify_agent_key
from app.core.database import get_db
from app.models import CatAgente, CatJobMonitoreado, CatPasoMonitoreado, JobsPasoEjecucion, PasoHorarioEsperado
from app.schemas.operacion import JobPasoEjecucionCreate, JobPasoEjecucionOut
from app.services.incidencias_service import crear_o_reutilizar_incidencia_servidor

router = APIRouter(prefix="/jobs", tags=["jobs"])


def resolver_estado_pendiente(body: JobPasoEjecucionCreate, horario: PasoHorarioEsperado | None, ahora: datetime) -> tuple[str, str | None]:
    if body.estado != "PENDIENTE" or horario is None:
        return body.estado, body.mensaje
    if not horario.dia_aplica:
        return "NO_APLICA", body.mensaje
    vencimiento = datetime.combine(body.fecha_ejecucion, horario.hora_esperada, tzinfo=ahora.tzinfo) + timedelta(minutes=horario.tolerancia_minutos)
    if ahora >= vencimiento:
        detalle = body.mensaje or "No se encontró ejecución del paso"
        return "ERROR", f"{detalle}. Horario vencido: {vencimiento.isoformat()}"[:500]
    return "PENDIENTE", body.mensaje


@router.post("/ejecuciones", response_model=JobPasoEjecucionOut, status_code=200)
def reportar_ejecucion_job(
    body: JobPasoEjecucionCreate,
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> JobPasoEjecucionOut:
    fila = db.execute(
        select(CatPasoMonitoreado, CatJobMonitoreado)
        .join(CatJobMonitoreado, CatJobMonitoreado.job_monitoreado_id == CatPasoMonitoreado.job_monitoreado_id)
        .where(
            CatPasoMonitoreado.paso_monitoreado_id == body.paso_monitoreado_id,
            CatPasoMonitoreado.activo == True,  # noqa: E712
            CatJobMonitoreado.activo == True,  # noqa: E712
        )
    ).one_or_none()
    if fila is None:
        raise HTTPException(status_code=422, detail="PasoMonitoreadoId no existe")

    paso, job = fila
    if agente.servidor_id != job.servidor_id:
        raise HTTPException(status_code=403, detail="El paso no pertenece al servidor del agente")

    horario = db.scalar(select(PasoHorarioEsperado).where(
        PasoHorarioEsperado.paso_monitoreado_id == body.paso_monitoreado_id,
        PasoHorarioEsperado.dia_semana == body.fecha_ejecucion.isoweekday(),
        PasoHorarioEsperado.hora_esperada == body.hora_esperada,
    ))
    estado, mensaje = resolver_estado_pendiente(body, horario, datetime.now(ZoneInfo("America/Mexico_City")))
    datos = body.model_dump(exclude={"paso_monitoreado_id", "fecha_ejecucion", "hora_esperada"})
    datos.update(estado=estado, mensaje=mensaje)

    def aplicar(ejecucion: JobsPasoEjecucion) -> None:
        for campo, valor in datos.items():
            setattr(ejecucion, campo, valor)

    ejecucion = db.scalar(
        select(JobsPasoEjecucion).where(
            JobsPasoEjecucion.paso_monitoreado_id == body.paso_monitoreado_id,
            JobsPasoEjecucion.fecha_ejecucion == body.fecha_ejecucion,
            JobsPasoEjecucion.hora_esperada == body.hora_esperada,
        )
    )
    if ejecucion is not None:
        aplicar(ejecucion)
    else:
        ejecucion = JobsPasoEjecucion(
            paso_monitoreado_id=body.paso_monitoreado_id,
            fecha_ejecucion=body.fecha_ejecucion,
            hora_esperada=body.hora_esperada,
            **datos,
        )
        db.add(ejecucion)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            ejecucion = db.scalar(
                select(JobsPasoEjecucion).where(
                    JobsPasoEjecucion.paso_monitoreado_id == body.paso_monitoreado_id,
                    JobsPasoEjecucion.fecha_ejecucion == body.fecha_ejecucion,
                    JobsPasoEjecucion.hora_esperada == body.hora_esperada,
                )
            )
            if ejecucion is None:
                raise
            aplicar(ejecucion)

    if estado == "ERROR" and ejecucion.incidencia_id is None:
        incidencia = crear_o_reutilizar_incidencia_servidor(
            db,
            servidor_id=job.servidor_id,
            servidor_nombre=f"ServidorId {job.servidor_id}",
            tipo_codigo="JOB_SQL_AGENT",
            fecha=body.fecha_ejecucion,
            problema=f"SQL Agent: {job.nombre_job} / {paso.nombre_paso} en ERROR",
            detalle=body.mensaje,
        )
        ejecucion.incidencia_id = incidencia.incidencia_id

    db.commit()
    db.refresh(ejecucion)
    return JobPasoEjecucionOut.model_validate(ejecucion)
