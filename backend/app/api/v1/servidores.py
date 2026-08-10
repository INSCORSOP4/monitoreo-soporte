"""Servidores — cat_servidores (§2, §4)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CatServidor
from app.schemas.catalogos import ServidorCreate, ServidorOut

router = APIRouter(prefix="/servidores", tags=["servidores"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ServidorOut])
def listar_servidores(activo: bool | None = None, db: Session = Depends(get_db)) -> list[ServidorOut]:
    stmt = select(CatServidor).order_by(CatServidor.nombre)
    if activo is not None:
        stmt = stmt.where(CatServidor.activo == activo)
    return [ServidorOut.model_validate(s) for s in db.scalars(stmt).all()]


@router.get("/{servidor_id}", response_model=ServidorOut)
def obtener_servidor(servidor_id: int, db: Session = Depends(get_db)) -> ServidorOut:
    servidor = db.get(CatServidor, servidor_id)
    if servidor is None:
        raise HTTPException(status_code=404, detail="Servidor no encontrado")
    return ServidorOut.model_validate(servidor)


@router.post("", response_model=ServidorOut, status_code=201)
def crear_servidor(body: ServidorCreate, db: Session = Depends(get_db)) -> ServidorOut:
    existente = db.scalar(select(CatServidor).where(CatServidor.nombre == body.nombre))
    if existente:
        raise HTTPException(status_code=409, detail="El servidor ya existe")
    servidor = CatServidor(**body.model_dump())
    db.add(servidor)
    db.commit()
    db.refresh(servidor)
    return ServidorOut.model_validate(servidor)
