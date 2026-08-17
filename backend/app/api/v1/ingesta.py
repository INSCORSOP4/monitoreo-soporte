"""Ingesta de AGENTES (§8, §24) — los agentes reportan al backend.

Autenticación: header X-Agent-Key (API key del agente, NO JWT de humano).
Los endpoints de ingesta usan verify_agent_key; el agente autenticado
se entrega como dependencia para registrar el reporte con su identidad.

Endpoints:
  GET  /ingesta/agente               -> identidad del agente (prueba del middleware)
  GET  /ingesta/configuracion        -> catálogo completo para validar (§35: el agente
                                         no tiene configuración quemada, la lee aquí)
  GET  /ingesta/pendientes-transferir -> ejecuciones OK sin transferencia COMPLETADA
                                         (lo consume el NAS Transfer Worker, §11/§30)
"""
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps_agent import verify_agent_key
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    CatAgente,
    CatBaseDatos,
    CatGrupoRespaldo,
    CatJobMonitoreado,
    CatPasoMonitoreado,
    HorarioEsperado,
    PasoHorarioEsperado,
    RespaldoEjecucion,
    RutaOrigenDestino,
    Transferencia,
)
from app.schemas.ingesta import ConfiguracionIngestaOut
from app.schemas.transferencias import PendientesTransferirOut

logger = get_logger(__name__)

router = APIRouter(prefix="/ingesta", tags=["ingesta"])


@router.get("/agente")
def identificar_agente(agente: CatAgente = Depends(verify_agent_key)) -> dict:
    """Confirma la identidad del agente autenticado (prueba del middleware)."""
    return {
        "agente_id": agente.agente_id,
        "nombre": agente.nombre,
        "activo": agente.activo,
    }


@router.get("/configuracion", response_model=ConfiguracionIngestaOut)
def configuracion_ingesta(
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> ConfiguracionIngestaOut:
    """Catálogo completo (bases activas + ruta origen/destino + horarios).

    El agente lo usa para saber QUÉ validar y CÓMO (tipo esperado por día,
    hora esperada, tolerancia). Solo bases Activo=1.
    """
    filas = db.execute(
        select(CatBaseDatos, CatGrupoRespaldo)
        .join(CatGrupoRespaldo, CatGrupoRespaldo.grupo_respaldo_id == CatBaseDatos.grupo_respaldo_id)
        .where(CatBaseDatos.activo == True)  # noqa: E712  (SQL Server: = 1)
        .order_by(CatBaseDatos.nombre_base)
    ).all()

    rutas = {
        r.base_datos_id: r
        for r in db.scalars(select(RutaOrigenDestino).where(RutaOrigenDestino.activo == True))  # noqa: E712
    }
    horarios: dict[int, list[HorarioEsperado]] = defaultdict(list)
    for h in db.scalars(select(HorarioEsperado).where(HorarioEsperado.activo == True)):  # noqa: E712
        horarios[h.base_datos_id].append(h)

    bases = []
    for base, grupo in filas:
        ruta = rutas.get(base.base_datos_id)
        bases.append(
            {
                "base_datos_id": base.base_datos_id,
                "grupo_respaldo_id": base.grupo_respaldo_id,
                "grupo_codigo": grupo.codigo,
                "nombre_base": base.nombre_base,
                "tipo_fuente": base.tipo_fuente,
                "tipo_backup_predeterminado": base.tipo_backup_predeterminado,
                "activo": base.activo,
                "ruta_origen": ruta.ruta_origen if ruta else None,
                "ruta_destino": ruta.ruta_destino if ruta else None,
                "horarios": [
                    {
                        "dia_semana": h.dia_semana,
                        "dia_aplica": bool(h.dia_aplica),
                        "tipo_backup_esperado": h.tipo_backup_esperado,
                        "hora_esperada": h.hora_esperada.strftime("%H:%M"),
                        "tolerancia_minutos": h.tolerancia_minutos,
                    }
                    for h in sorted(horarios.get(base.base_datos_id, []), key=lambda x: x.dia_semana)
                ],
            }
        )

    jobs_pasos = []
    if agente.servidor_id is not None:
        pasos = db.execute(
            select(CatPasoMonitoreado, CatJobMonitoreado)
            .join(CatJobMonitoreado, CatJobMonitoreado.job_monitoreado_id == CatPasoMonitoreado.job_monitoreado_id)
            .where(
                CatJobMonitoreado.servidor_id == agente.servidor_id,
                CatJobMonitoreado.activo == True,  # noqa: E712
                CatPasoMonitoreado.activo == True,  # noqa: E712
            )
            .order_by(CatJobMonitoreado.nombre_job, CatPasoMonitoreado.step_id)
        ).all()
        ids_pasos = [paso.paso_monitoreado_id for paso, _ in pasos]
        horarios_jobs = defaultdict(list)
        if ids_pasos:
            for horario in db.scalars(
                select(PasoHorarioEsperado)
                .where(PasoHorarioEsperado.paso_monitoreado_id.in_(ids_pasos))
                .order_by(PasoHorarioEsperado.dia_semana, PasoHorarioEsperado.hora_esperada)
            ):
                horarios_jobs[horario.paso_monitoreado_id].append(horario)
        jobs_pasos = [
            {
                "paso_monitoreado_id": paso.paso_monitoreado_id,
                "job_monitoreado_id": job.job_monitoreado_id,
                "nombre_job": job.nombre_job,
                "step_id": paso.step_id,
                "nombre_paso": paso.nombre_paso,
                "horarios": [
                    {
                        "dia_semana": h.dia_semana,
                        "dia_aplica": h.dia_aplica,
                        "tipo_backup_esperado": "JOB_SQL_AGENT",
                        "hora_esperada": h.hora_esperada.strftime("%H:%M"),
                        "tolerancia_minutos": h.tolerancia_minutos,
                    }
                    for h in horarios_jobs[paso.paso_monitoreado_id]
                ],
            }
            for paso, job in pasos
        ]

    logger.info("Configuración entregada a %s: %s bases", agente.nombre, len(bases))
    return ConfiguracionIngestaOut(
        agente_id=agente.agente_id,
        agente_nombre=agente.nombre,
        servidor_id=agente.servidor_id,
        generado_en=datetime.now(timezone.utc).isoformat(),
        bases=bases,
        jobs_pasos=jobs_pasos,
        disco_warning_pct=settings.disk_warning_pct,
        disco_error_pct=settings.disk_error_pct,
    )


@router.get("/pendientes-transferir", response_model=PendientesTransferirOut)
def pendientes_transferir(
    fecha: date,
    agente: CatAgente = Depends(verify_agent_key),
    db: Session = Depends(get_db),
) -> PendientesTransferirOut:
    """Ejecuciones listas para transferir al NAS (§11) o para terminar su borrado (§30).

    Criterio: respaldos_ejecuciones con Estado='OK' (ya validados por el checker)
    y ArchivoEncontrado definido, que NO estén totalmente terminados (COMPLETADA
    con OrigenEliminado=1). Dos modos:

    - solo_eliminar=False: sin transferencia COMPLETADA — el worker copia al NAS
      y confirma (flujo §11). Incluye la transferencia previa NO completada
      (FALLIDA/EN_PROGRESO) para calcular RetryNumber y actualizar en vez de
      duplicar (reintento §13 entre corridas).
    - solo_eliminar=True: existe COMPLETADA pero OrigenEliminado=0 (el borrado
      falló en una corrida previa, ej. archivo en uso). El worker reintenta SOLO
      la eliminación sin re-copiar (§30 recuperación) — nunca queda un origen
      huérfano sin que nadie se entere.

    El worker nunca recibe bases sin ruta registrada en rutas_origen_destino
    (nada de operar fuera del catálogo — §5 rutas estrictas).
    """
    terminadas = select(Transferencia.ejecucion_id).where(
        Transferencia.estado == "COMPLETADA",
        Transferencia.origen_eliminado == True,  # noqa: E712
    )
    filas = db.execute(
        select(RespaldoEjecucion, CatBaseDatos, RutaOrigenDestino)
        .join(CatBaseDatos, CatBaseDatos.base_datos_id == RespaldoEjecucion.base_datos_id)
        .join(RutaOrigenDestino, RutaOrigenDestino.base_datos_id == RespaldoEjecucion.base_datos_id)
        .where(
            RespaldoEjecucion.fecha_ejecucion == fecha,
            RespaldoEjecucion.estado == "OK",
            RespaldoEjecucion.archivo_encontrado.is_not(None),
            RespaldoEjecucion.ejecucion_id.not_in(terminadas),
            RutaOrigenDestino.activo == True,  # noqa: E712
        )
        .order_by(CatBaseDatos.nombre_base)
    ).all()

    ids = [ej.ejecucion_id for ej, _, _ in filas]
    trans_por_ejecucion: dict[int, list[Transferencia]] = defaultdict(list)
    if ids:
        for t in db.scalars(select(Transferencia).where(Transferencia.ejecucion_id.in_(ids))).all():
            trans_por_ejecucion[t.ejecucion_id].append(t)

    items = []
    for ejecucion, base, ruta in filas:
        tran = trans_por_ejecucion.get(ejecucion.ejecucion_id, [])
        completada_sin_borrar = [t for t in tran if t.estado == "COMPLETADA" and not t.origen_eliminado]
        solo_eliminar = len(completada_sin_borrar) > 0
        if solo_eliminar:
            # upsert sobre la MISMA fila COMPLETADA (retry_number original)
            previa = max(completada_sin_borrar, key=lambda t: t.retry_number)
        else:
            previa = max(tran, key=lambda t: t.retry_number) if tran else None
        items.append(
            {
                "ejecucion_id": ejecucion.ejecucion_id,
                "base_datos_id": base.base_datos_id,
                "nombre_base": base.nombre_base,
                "grupo_codigo": None,
                "archivo_encontrado": ejecucion.archivo_encontrado,
                "tamano_bytes": ejecucion.tamano_bytes,
                "fecha_generacion": ejecucion.fecha_generacion.isoformat(sep="T", timespec="seconds")
                if ejecucion.fecha_generacion
                else None,
                "ruta_origen": ruta.ruta_origen,
                "ruta_destino": ruta.ruta_destino,
                "eliminar_origen_tras_transferencia": bool(ruta.eliminar_origen_tras_transferencia),
                "solo_eliminar": solo_eliminar,
                "transferencia_existente": (
                    {
                        "transferencia_id": previa.transferencia_id,
                        "estado": previa.estado,
                        "retry_number": previa.retry_number,
                    }
                    if previa is not None
                    else None
                ),
            }
        )

    logger.info(
        "%s consultó pendientes de transferencia (%s): %s items",
        agente.nombre, fecha, len(items),
    )
    return PendientesTransferirOut(
        fecha=fecha.isoformat(),
        agente_id=agente.agente_id,
        agente_nombre=agente.nombre,
        items=items,
    )
