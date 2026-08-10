"""Roles — cat_roles (catálogo de roles del sistema, §22)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CatRol
from app.schemas.catalogos import RolOut

router = APIRouter(prefix="/roles", tags=["roles"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[RolOut])
def listar_roles(activo: bool | None = None, db: Session = Depends(get_db)) -> list[RolOut]:
    stmt = select(CatRol).order_by(CatRol.rol_id)
    if activo is not None:
        stmt = stmt.where(CatRol.activo == activo)
    return [RolOut.model_validate(r) for r in db.scalars(stmt).all()]
