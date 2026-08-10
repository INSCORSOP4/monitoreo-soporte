"""Agentes — cat_agentes (§8). Los agentes son MÁQUINAS, no personas.

Flujo:
  POST /api/v1/agentes  -> crea el agente y devuelve la API key EN CLARO
                           (única vez; solo se persiste su hash bcrypt).
  GET  /api/v1/agentes  -> lista agentes sin exponer ApiKeyHash.

La autenticación de agentes (X-API-Key) se validará en el endpoint de ingesta
de reportes (Fase 4) usando verify_api_key contra ApiKeyHash.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import generate_api_key, hash_api_key
from app.models import CatAgente
from app.schemas.agentes import AgenteCreate, AgenteOut, AgenteWithApiKey

router = APIRouter(prefix="/agentes", tags=["agentes"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=AgenteWithApiKey, status_code=201)
def crear_agente(body: AgenteCreate, db: Session = Depends(get_db)) -> AgenteWithApiKey:
    existente = db.scalar(select(CatAgente).where(CatAgente.nombre == body.nombre))
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un agente con ese nombre")

    api_key = generate_api_key()
    agente = CatAgente(
        nombre=body.nombre,
        api_key_hash=hash_api_key(api_key),
        activo=body.activo,
    )
    db.add(agente)
    db.commit()
    db.refresh(agente)

    # La API key en claro se devuelve UNA sola vez; solo el hash queda en BD.
    return AgenteWithApiKey(
        agente_id=agente.agente_id,
        nombre=agente.nombre,
        activo=agente.activo,
        api_key=api_key,
    )


@router.get("", response_model=list[AgenteOut])
def listar_agentes(activo: bool | None = None, db: Session = Depends(get_db)) -> list[AgenteOut]:
    stmt = select(CatAgente).order_by(CatAgente.nombre)
    if activo is not None:
        stmt = stmt.where(CatAgente.activo == activo)
    return [AgenteOut.model_validate(a) for a in db.scalars(stmt).all()]
