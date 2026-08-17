"""Alertas — bitácora de envíos (§28)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Alerta
from app.schemas.operacion import AlertaOut
from app.services import alertas_service

router = APIRouter(prefix="/alertas", tags=["alertas"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[AlertaOut])
def listar_alertas(
    incidencia_id: int | None = None,
    ejecucion_id: int | None = None,
    lectura_disco_id: int | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
) -> list[AlertaOut]:
    stmt = select(Alerta).order_by(Alerta.alerta_id.desc())
    if incidencia_id is not None:
        stmt = stmt.where(Alerta.incidencia_id == incidencia_id)
    if ejecucion_id is not None:
        stmt = stmt.where(Alerta.ejecucion_id == ejecucion_id)
    if lectura_disco_id is not None:
        stmt = stmt.where(Alerta.lectura_disco_id == lectura_disco_id)
    if estado is not None:
        stmt = stmt.where(Alerta.estado == estado)
    return [AlertaOut.model_validate(a) for a in db.scalars(stmt).all()]


@router.post("/{alerta_id}/reintentar", status_code=status.HTTP_202_ACCEPTED)
def reintentar_alerta(
    alerta_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    if alerta.estado != "FALLIDA":
        raise HTTPException(status_code=409, detail="Solo se pueden reintentar alertas FALLIDA")

    alerta.estado = "PENDIENTE"
    alerta.error_detalle = None
    db.commit()

    background_tasks.add_task(alertas_service.enviar_alerta, alerta_id)
    return {"alerta_id": alerta_id, "estado": "PENDIENTE"}
