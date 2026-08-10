"""Usuarios — cat_usuarios (usuarios locales con hash bcrypt)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
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
    # La unicidad del Correo (y del UsuarioExternoId) la garantiza la base de datos
    # (UQ_cat_usuarios_Correo + índice único filtrado). Solo capturamos el error.
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Distinguimos el origen del error: correo duplicado, usuario externo duplicado
        # o FK de rol inválida — con mensajes claros en lugar de un 422 genérico.
        err = str(exc.orig)
        if "UQ_cat_usuarios_Correo" in err:
            raise HTTPException(status_code=409, detail="El correo ya está registrado") from exc
        if "UQ_cat_usuarios_UsuarioExternoId" in err:
            raise HTTPException(
                status_code=409,
                detail="El UsuarioExternoId ya está registrado (usa 0 o null para usuarios locales)",
            ) from exc
        if "FK_cat_usuarios_Rol" in err:
            raise HTTPException(
                status_code=422,
                detail=f"rol_id {body.rol_id} no existe en cat_roles (consulta GET /api/v1/roles)",
            ) from exc
        raise HTTPException(
            status_code=422,
            detail="No se pudo crear el usuario (verifica rol_id y referencias)",
        ) from exc
    db.refresh(usuario)
    return UsuarioOut.model_validate(usuario)
