"""Discos — discos_lecturas (§33 Disco Checker).

Autenticación separada por endpoint:
  POST /discos/lecturas -> API key de AGENTE (verify_agent_key, §8).
                           Es el endpoint de ingesta del Disco Checker
                           (igual que POST /respaldos/ejecuciones).

Idempotente por (ServidorId, UnidadLetra, FechaLectura): reejecutar el checker
el mismo día actualiza la lectura en lugar de duplicar (UNIQUE de la tabla como
barrera definitiva, mismo patrón que respaldos_ejecuciones §35).

Incidencia automática (§26): si el agente reporta Estado=ERROR, el backend crea
(o reutiliza) una incidencia SISTEMA por (Servidor, Fecha) con TipoIncidenciaId
DISCO_SERVIDOR, y la vincula a la lectura (discos_lecturas.IncidenciaId).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps_agent import verify_agent_key
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import CatAgente, CatServidor, DiscosLectura
from app.schemas.operacion import DiscosLecturaCreate, DiscosLecturaOut
from app.services.incidencias_service import crear_o_reutilizar_incidencia_disco

logger = get_logger(__name__)

router = APIRouter(prefix="/discos", tags=["discos"])


@router.post("/lecturas", response_model=DiscosLecturaOut, status_code=200)
def reportar_lectura_disco(
    body: DiscosLecturaCreate,
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> DiscosLecturaOut:
    """Ingesta del Disco Checker (§33): registra la lectura diaria por unidad.

    Idempotente (§35): si ya existe (ServidorId, UnidadLetra, FechaLectura),
    actualiza los campos en lugar de duplicar. El UNIQUE de la tabla actúa como
    barrera definitiva ante carreras (dos requests concurrentes): si el INSERT
    choca, se captura IntegrityError y se reaplica como UPDATE.

    Incidencia automática (§26): si el estado es ERROR, el backend crea (o
    reutiliza) la incidencia con DetectadaPor='SISTEMA', TipoIncidenciaId
    DISCO_SERVIDOR y ServidorId (BaseDatosId=NULL) — una por (servidor, fecha).
    El agente no reporta incidencias: solo hechos.
    """
    servidor = db.get(CatServidor, body.servidor_id)
    if servidor is None:
        raise HTTPException(status_code=422, detail=f"ServidorId {body.servidor_id} no existe")

    datos = body.model_dump(exclude={"servidor_id", "unidad_letra", "fecha_lectura"})
    logger.info(
        "Ingesta disco de %s: servidor %s (%s), unidad %s, fecha %s, estado %s, libre %.2f%%",
        agente.nombre,
        body.servidor_id,
        servidor.nombre,
        body.unidad_letra,
        body.fecha_lectura,
        body.estado,
        body.porcentaje_libre,
    )

    def _aplicar(_lectura: DiscosLectura) -> None:
        for campo, valor in datos.items():
            setattr(_lectura, campo, valor)

    lectura = db.scalar(
        select(DiscosLectura).where(
            DiscosLectura.servidor_id == body.servidor_id,
            DiscosLectura.unidad_letra == body.unidad_letra,
            DiscosLectura.fecha_lectura == body.fecha_lectura,
        )
    )
    if lectura is not None:
        _aplicar(lectura)
    else:
        lectura = DiscosLectura(
            servidor_id=body.servidor_id,
            unidad_letra=body.unidad_letra,
            fecha_lectura=body.fecha_lectura,
            **datos,
        )
        db.add(lectura)
        try:
            db.flush()
        except IntegrityError:
            # Carrera: otra request insertó la misma (Servidor, Unidad, Fecha).
            db.rollback()
            lectura = db.scalar(
                select(DiscosLectura).where(
                    DiscosLectura.servidor_id == body.servidor_id,
                    DiscosLectura.unidad_letra == body.unidad_letra,
                    DiscosLectura.fecha_lectura == body.fecha_lectura,
                )
            )
            if lectura is None:
                raise
            _aplicar(lectura)

    # §26: cada ERROR reportado genera una incidencia automática (idempotente),
    # vinculada al servidor. La misma incidencia abierta cubre varias unidades
    # del mismo servidor el mismo día (barrera BD UQ_incidencias_DISCO_*).
    if body.estado == "ERROR":
        incidencia = crear_o_reutilizar_incidencia_disco(
            db,
            servidor=servidor,
            fecha=body.fecha_lectura,
            problema=f"Espacio en disco bajo en {servidor.nombre} ({body.unidad_letra})",
            detalle=(
                f"Reportado por {agente.nombre}. Lectura #{lectura.lectura_id}, "
                f"unidad {body.unidad_letra}: {body.espacio_libre_gb:,.2f} GB libres de "
                f"{body.espacio_total_gb:,.2f} GB ({body.porcentaje_libre:.2f}%). "
                f"{body.detalle or ''}"
            ),
        )
        lectura.incidencia_id = incidencia.incidencia_id

    db.commit()
    db.refresh(lectura)
    return DiscosLecturaOut.model_validate(lectura)
