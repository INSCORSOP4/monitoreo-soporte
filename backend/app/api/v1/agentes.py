"""Agentes — cat_agentes (§8). Los agentes son MÁQUINAS, no personas.

Flujo:
  POST /api/v1/agentes  -> crea el agente y devuelve la API key EN CLARO
                           (única vez; solo se persiste su hash bcrypt).
                           Formato: '<AgenteId>.<secreto>' (ver security.py).
  GET  /api/v1/agentes  -> lista agentes sin exponer ApiKeyHash.

La autenticación de agentes (X-Agent-Key) se valida en los endpoints de
ingesta con verify_agent_key contra ApiKeyHash.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import compose_api_key, generate_secreto, hash_api_key
from app.models import CatAgente
from app.schemas.agentes import AgenteCreate, AgenteOut, AgenteWithApiKey

router = APIRouter(prefix="/agentes", tags=["agentes"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=AgenteWithApiKey, status_code=201)
def crear_agente(body: AgenteCreate, db: Session = Depends(get_db)) -> AgenteWithApiKey:
    existente = db.scalar(select(CatAgente).where(CatAgente.nombre == body.nombre))
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un agente con ese nombre")

    # El secreto se genera ANTES del INSERT; el hash persiste solo el secreto.
    secreto = generate_secreto()
    agente = CatAgente(
        nombre=body.nombre,
        api_key_hash=hash_api_key(secreto),
        activo=body.activo,
    )
    db.add(agente)
    try:
        db.flush()  # obtiene AgenteId para componer la key '<AgenteId>.<secreto>'
    except IntegrityError:
        # Carrera: otra request creó el mismo nombre entre el SELECT y el INSERT.
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un agente con ese nombre") from None
    api_key = compose_api_key(agente.agente_id, secreto)
    db.commit()

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
