"""Responsables del día (§21) — consulta y asignación para el dashboard.

GET /responsables-dia/hoy (JWT humano): devuelve quién es el responsable de la
fecha (por defecto hoy) y DISPARA la asignación automática si aún no existe —
así el dashboard muestra al responsable sin esperar a que llegue una incidencia.

PUT /responsables-dia/{fecha} (solo Coordinador/Administrador): fija el
UsuarioId manualmente con OrigenAsignacion='MANUAL' y registra quién reasignó
(UsuarioReasignoId). Una vez MANUAL, la lógica automática nunca lo sobrescribe:
la fila ya existe y el lazy assignment solo actúa cuando NO existe.

La política completa vive en responsables_service (solo días hábiles, rotación,
fila existente respetada): este endpoint solo la invoca y devuelve el resultado
con el nombre del usuario para mostrarlo directo.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import CatUsuario, ResponsableDia
from app.schemas.operacion import ResponsableDiaAsignarCreate, ResponsableDiaOut
from app.services.responsables_service import obtener_o_crear_responsable_dia

logger = get_logger(__name__)

_ROLES_ASIGNACION = ("COORDINADOR", "ADMINISTRADOR")

router = APIRouter(prefix="/responsables-dia", tags=["responsables-dia"], dependencies=[Depends(get_current_user)])


def _rol_autorizado(usuario: dict) -> None:
    """Solo Coordinador/Administrador pueden reasignar manualmente (§21)."""
    if usuario.get("rol") not in _ROLES_ASIGNACION:
        raise HTTPException(
            status_code=403,
            detail=f"Rol no autorizado para reasignar el responsable del día (requiere {', '.join(_ROLES_ASIGNACION)})",
        )


@router.get("/hoy")
def responsable_hoy(
    fecha: date | None = Query(default=None, description="Override de prueba (defecto: hoy)"),
    db: Session = Depends(get_db),
) -> dict:
    """Responsable de la fecha, disparando la asignación automática si falta.

    Si aún no existe fila en responsables_dia para la fecha, la crea por
    rotación (solo días hábiles; fin de semana -> responsable null). Devuelve el
    usuario y su nombre para el dashboard.
    """
    fecha_obj = fecha or date.today()
    usuario_id = obtener_o_crear_responsable_dia(db, fecha_obj)
    db.commit()  # persiste la asignación AUTO creada (si aplicó)

    fila = db.scalar(select(ResponsableDia).where(ResponsableDia.fecha == fecha_obj))
    nombre = None
    if usuario_id is not None:
        nombre = db.scalar(select(CatUsuario.nombre_completo).where(CatUsuario.usuario_id == usuario_id))

    return {
        "fecha": fecha_obj.isoformat(),
        "responsable": {
            "usuario_id": usuario_id,
            "nombre": nombre,
        }
        if usuario_id is not None
        else None,
        "origen_asignacion": fila.origen_asignacion if fila else None,
    }


@router.put("/{fecha}", response_model=ResponsableDiaOut)
def asignar_manual(
    fecha: date,
    body: ResponsableDiaAsignarCreate,
    usuario: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResponsableDiaOut:
    """Fija el responsable de la fecha manualmente (OrigenAsignacion='MANUAL').

    Solo Coordinador/Administrador. Upsert: crea la fila si no existe o
    actualiza la existente (AUTO o MANUAL). Registra UsuarioReasignoId = quien
    reasignó. Una vez MANUAL, la asignación automática no la toca nunca más.
    """
    _rol_autorizado(usuario)

    if db.get(CatUsuario, body.usuario_id) is None:
        raise HTTPException(status_code=422, detail=f"UsuarioId {body.usuario_id} no existe")

    # El JWT trae usuario_id del catálogo (extra claim, §22); si por algún motivo
    # no viene (stub/token viejo), se registra la reasignación sin identificar quién.
    reasigno_id = usuario.get("usuario_id")

    fila = db.scalar(select(ResponsableDia).where(ResponsableDia.fecha == fecha))
    if fila is None:
        fila = ResponsableDia(
            fecha=fecha,
            usuario_id=body.usuario_id,
            origen_asignacion="MANUAL",
            usuario_reasigno_id=reasigno_id,
        )
        db.add(fila)
        logger.info(
            "Asignación MANUAL creada para %s: usuario %s (reasignó usuario_id %s)",
            fecha, body.usuario_id, reasigno_id,
        )
    else:
        fila.usuario_id = body.usuario_id
        fila.origen_asignacion = "MANUAL"
        fila.usuario_reasigno_id = reasigno_id
        logger.info(
            "Asignación MANUAL actualizada para %s: usuario %s (antes %s/%s; reasignó usuario_id %s)",
            fecha, body.usuario_id, fila.usuario_id, fila.origen_asignacion, reasigno_id,
        )

    db.commit()
    db.refresh(fila)
    nombre = db.scalar(select(CatUsuario.nombre_completo).where(CatUsuario.usuario_id == fila.usuario_id))
    return ResponsableDiaOut(
        fecha=fila.fecha,
        usuario_id=fila.usuario_id,
        origen_asignacion=fila.origen_asignacion,
        usuario_reasigno_id=fila.usuario_reasigno_id,
        fecha_asignacion=fila.fecha_asignacion,
        nombre=nombre,
    )
