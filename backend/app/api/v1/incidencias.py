"""Incidencias — incidencias y acciones_incidencia (§26)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AccionIncidencia, Incidencia
from app.schemas.operacion import AccionIncidenciaCreate, IncidenciaCreate, IncidenciaOut

router = APIRouter(prefix="/incidencias", tags=["incidencias"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[IncidenciaOut])
def listar_incidencias(
    estado: str | None = None,
    fecha: date | None = None,
    base_datos_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[IncidenciaOut]:
    stmt = select(Incidencia).order_by(Incidencia.incidencia_id.desc())
    if estado is not None:
        stmt = stmt.where(Incidencia.estado == estado)
    if fecha is not None:
        stmt = stmt.where(Incidencia.fecha_incidencia == fecha)
    if base_datos_id is not None:
        stmt = stmt.where(Incidencia.base_datos_id == base_datos_id)
    return [IncidenciaOut.model_validate(i) for i in db.scalars(stmt).all()]


@router.get("/{incidencia_id}", response_model=IncidenciaOut)
def obtener_incidencia(incidencia_id: int, db: Session = Depends(get_db)) -> IncidenciaOut:
    incidencia = db.get(Incidencia, incidencia_id)
    if incidencia is None:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return IncidenciaOut.model_validate(incidencia)


@router.post("", response_model=IncidenciaOut, status_code=201)
def crear_incidencia(body: IncidenciaCreate, db: Session = Depends(get_db)) -> IncidenciaOut:
    incidencia = Incidencia(
        tipo_incidencia_id=body.tipo_incidencia_id,
        servidor_id=body.servidor_id,
        base_datos_id=body.base_datos_id,
        fecha_incidencia=body.fecha_incidencia,
        problema=body.problema,
        detalle=body.detalle,
        estado="ABIERTA",
        detectada_por="USUARIO",
    )
    db.add(incidencia)
    db.commit()
    db.refresh(incidencia)
    return IncidenciaOut.model_validate(incidencia)


@router.post("/{incidencia_id}/acciones", response_model=dict, status_code=201)
def registrar_accion(incidencia_id: int, body: AccionIncidenciaCreate, db: Session = Depends(get_db)) -> dict:
    incidencia = db.get(Incidencia, incidencia_id)
    if incidencia is None:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    accion = AccionIncidencia(
        incidencia_id=incidencia_id,
        usuario_id=body.usuario_id,
        descripcion=body.descripcion,
        resultado=body.resultado,
    )
    db.add(accion)
    # §26: al registrar una acción con resultado CORRECTO se cierra la incidencia
    if body.resultado == "CORRECTO":
        incidencia.estado = "RESUELTA"
        incidencia.resultado = body.resultado
    db.commit()
    return {"success": True, "accion_incidencia_id": accion.accion_incidencia_id}
