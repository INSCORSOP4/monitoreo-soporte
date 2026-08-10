"""Bases de datos — cat_bases_datos (§9: 41 RESTO, §10: 3 FORTIA)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CatBaseDatos
from app.schemas.catalogos import BaseDatosCreate, BaseDatosOut

router = APIRouter(prefix="/bases-datos", tags=["bases_datos"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[BaseDatosOut])
def listar_bases(
    grupo_respaldo_id: int | None = None,
    activo: bool | None = None,
    db: Session = Depends(get_db),
) -> list[BaseDatosOut]:
    stmt = select(CatBaseDatos).order_by(CatBaseDatos.nombre_base)
    if grupo_respaldo_id is not None:
        stmt = stmt.where(CatBaseDatos.grupo_respaldo_id == grupo_respaldo_id)
    if activo is not None:
        stmt = stmt.where(CatBaseDatos.activo == activo)
    return [BaseDatosOut.model_validate(b) for b in db.scalars(stmt).all()]


@router.get("/{base_datos_id}", response_model=BaseDatosOut)
def obtener_base(base_datos_id: int, db: Session = Depends(get_db)) -> BaseDatosOut:
    base = db.get(CatBaseDatos, base_datos_id)
    if base is None:
        raise HTTPException(status_code=404, detail="Base de datos no encontrada")
    return BaseDatosOut.model_validate(base)


@router.post("", response_model=BaseDatosOut, status_code=201)
def crear_base(body: BaseDatosCreate, db: Session = Depends(get_db)) -> BaseDatosOut:
    existente = db.scalar(
        select(CatBaseDatos).where(
            CatBaseDatos.grupo_respaldo_id == body.grupo_respaldo_id,
            CatBaseDatos.nombre_base == body.nombre_base,
        )
    )
    if existente:
        raise HTTPException(status_code=409, detail="La base ya existe en el grupo")
    base = CatBaseDatos(**body.model_dump())
    db.add(base)
    db.commit()
    db.refresh(base)
    return BaseDatosOut.model_validate(base)
