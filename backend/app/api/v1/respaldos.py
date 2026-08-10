"""Respaldos — respaldos_ejecuciones (bitácora digital §24)."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CatBaseDatos, CatGrupoRespaldo, RespaldoEjecucion
from app.schemas.operacion import RespaldoEjecucionOut

router = APIRouter(prefix="/respaldos", tags=["respaldos"], dependencies=[Depends(get_current_user)])


@router.get("/ejecuciones", response_model=list[RespaldoEjecucionOut])
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


@router.get("/resumen")
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
