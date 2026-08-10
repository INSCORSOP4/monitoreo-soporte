"""Historial — auditoría (§27)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Historial
from app.schemas.operacion import HistorialOut

router = APIRouter(prefix="/historial", tags=["historial"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[HistorialOut])
def listar_historial(
    entidad: str | None = None,
    tipo_evento: str | None = None,
    limite: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[HistorialOut]:
    stmt = select(Historial).order_by(Historial.historial_id.desc()).limit(limite)
    if entidad is not None:
        stmt = stmt.where(Historial.entidad == entidad)
    if tipo_evento is not None:
        stmt = stmt.where(Historial.tipo_evento == tipo_evento)
    return [HistorialOut.model_validate(h) for h in db.scalars(stmt).all()]
