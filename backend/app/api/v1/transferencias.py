"""Transferencias SQL -> NAS (§11, §30) — movimiento de respaldos ya validados.

Autenticación separada por endpoint:
  POST /transferencias          -> API key de AGENTE (verify_agent_key, §8):
                                    lo reporta el NAS Transfer Worker (10.0.3.8).
  GET  /transferencias          -> JWT de humano (get_current_user): bitácora §24.

Regla crítica §30: `OrigenEliminado=1` SOLO es válido cuando la transferencia
quedó COMPLETADA con la validación aprobada: hash coincidente (cuando se
solicitó) o hash no solicitado con tamaño/fecha confirmados (HASH_VALIDACION=false).
Nunca copiar->eliminar: el backend se niega a registrar lo contrario, aunque
el agente esté mal configurado.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.deps_agent import verify_agent_key
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import CatAgente, RespaldoEjecucion, Transferencia
from app.schemas.transferencias import TransferenciaCreate, TransferenciaOut

logger = get_logger(__name__)

router = APIRouter(prefix="/transferencias", tags=["transferencias"])


@router.get("", response_model=list[TransferenciaOut], dependencies=[Depends(get_current_user)])
def listar_transferencias(
    fecha: date | None = None,
    base_datos_id: int | None = None,
    estado: str | None = None,
    db: Session = Depends(get_db),
) -> list[TransferenciaOut]:
    stmt = select(Transferencia).order_by(Transferencia.fecha_transferencia.desc())
    if fecha is not None:
        stmt = stmt.where(Transferencia.fecha_transferencia.cast(date) == fecha)
    if base_datos_id is not None:
        stmt = stmt.where(Transferencia.base_datos_id == base_datos_id)
    if estado is not None:
        stmt = stmt.where(Transferencia.estado == estado)
    return [TransferenciaOut.model_validate(t) for t in db.scalars(stmt).all()]


@router.post("", response_model=TransferenciaOut, status_code=201)
def reportar_transferencia(
    body: TransferenciaCreate,
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> TransferenciaOut:
    """Registra el resultado de una transferencia (idempotente por retry).

    - Valida que la ejecución exista y pertenezca a la base reportada.
    - §30: rechaza origen_eliminado=True si no es COMPLETADA con validación
      aprobada (hash coincidente, o hash no solicitado con tamaño/fecha OK).
    - Upsert por (EjecucionId, RetryNumber): reenvíos del mismo intento actualizan
      en vez de duplicar; cada reintento del worker es una fila nueva (auditoría).
    """
    if body.origen_eliminado and (
        body.estado != "COMPLETADA"
        or body.hash_coincide is False
        or (body.hash_coincide is None and (body.hash_origen is not None or body.hash_destino is not None))
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "OrigenEliminado=1 solo es válido con Estado='COMPLETADA' y validación "
                "de integridad aprobada: hash coincidente, o hash no solicitado "
                "(HASH_VALIDACION=false: tamaño+fecha ya confirmados en destino)."
            ),
        )

    ejecucion = db.get(RespaldoEjecucion, body.ejecucion_id)
    if ejecucion is None or ejecucion.base_datos_id != body.base_datos_id:
        raise HTTPException(
            status_code=422,
            detail=f"EjecucionId {body.ejecucion_id} no existe o no pertenece a BaseDatosId {body.base_datos_id}",
        )

    campos = body.model_dump(exclude={"ejecucion_id", "base_datos_id", "retry_number"})

    def _aplicar(t: Transferencia) -> None:
        for campo, valor in campos.items():
            setattr(t, campo, valor)

    transferencia = db.scalar(
        select(Transferencia).where(
            Transferencia.ejecucion_id == body.ejecucion_id,
            Transferencia.retry_number == body.retry_number,
        )
    )
    if transferencia is not None:
        _aplicar(transferencia)
    else:
        transferencia = Transferencia(
            ejecucion_id=body.ejecucion_id,
            base_datos_id=body.base_datos_id,
            retry_number=body.retry_number,
            **campos,
        )
        db.add(transferencia)

    logger.info(
        "Transferencia reportada por %s: ejecución %s, base %s, estado %s, "
        "origen_eliminado=%s, retry %s",
        agente.nombre,
        body.ejecucion_id,
        body.base_datos_id,
        body.estado,
        body.origen_eliminado,
        body.retry_number,
    )
    db.commit()
    db.refresh(transferencia)
    return TransferenciaOut.model_validate(transferencia)
