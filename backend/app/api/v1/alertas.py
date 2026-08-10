"""Alertas — bitácora de envíos (§28)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Alerta
from app.schemas.operacion import AlertaOut

router = APIRouter(prefix="/alertas", tags=["alertas"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[AlertaOut])
def listar_alertas(
    incidencia_id: int | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
) -> list[AlertaOut]:
    stmt = select(Alerta).order_by(Alerta.alerta_id.desc())
    if incidencia_id is not None:
        stmt = stmt.where(Alerta.incidencia_id == incidencia_id)
    if estado is not None:
        stmt = stmt.where(Alerta.estado == estado)
    return [AlertaOut.model_validate(a) for a in db.scalars(stmt).all()]
