"""Usuarios — cat_usuarios (usuarios locales con hash bcrypt)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models import CatUsuario
from app.schemas.catalogos import UsuarioCreate, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(activo: bool | None = None, db: Session = Depends(get_db)) -> list[UsuarioOut]:
    stmt = select(CatUsuario).order_by(CatUsuario.nombre_completo)
    if activo is not None:
        stmt = stmt.where(CatUsuario.activo == activo)
    return [UsuarioOut.model_validate(u) for u in db.scalars(stmt).all()]


@router.get("/{usuario_id}", response_model=UsuarioOut)
def obtener_usuario(usuario_id: int, db: Session = Depends(get_db)) -> UsuarioOut:
    usuario = db.get(CatUsuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UsuarioOut.model_validate(usuario)


@router.post("", response_model=UsuarioOut, status_code=201)
def crear_usuario(body: UsuarioCreate, db: Session = Depends(get_db)) -> UsuarioOut:
    # Unicidad: por UsuarioExternoId cuando existe (índice filtrado), y por
    # nombre_completo para los usuarios locales creados sin referencia externa.
    if body.usuario_externo_id is not None:
        existente = db.scalar(
            select(CatUsuario).where(CatUsuario.usuario_externo_id == body.usuario_externo_id)
        )
        if existente:
            raise HTTPException(status_code=409, detail="El usuario externo ya está registrado")
    existente = db.scalar(
        select(CatUsuario).where(CatUsuario.nombre_completo == body.nombre_completo)
    )
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese nombre")

    # La contraseña se guarda SOLO como hash bcrypt (nunca en claro, §35)
    password_hash = hash_password(body.password) if body.password else None
    usuario = CatUsuario(
        usuario_externo_id=body.usuario_externo_id,
        nombre_completo=body.nombre_completo,
        correo=body.correo,
        rol_id=body.rol_id,
        password_hash=password_hash,
        debe_cambiar_password=body.debe_cambiar_password,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return UsuarioOut.model_validate(usuario)
