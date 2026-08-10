"""Ingesta de AGENTES (§8, §24) — los agentes reportan al backend.

Autenticación: header X-Agent-Key (API key del agente, NO JWT de humano).
Los endpoints de ingesta usan verify_agent_key; el agente autenticado
se entrega como dependencia para registrar el reporte con su identidad.

Endpoints:
  GET  /ingesta/agente         -> identidad del agente (prueba del middleware)
  GET  /ingesta/configuracion  -> catálogo completo para validar (§35: el agente
                                   no tiene configuración quemada, la lee aquí)
"""
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps_agent import verify_agent_key
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import CatAgente, CatBaseDatos, CatGrupoRespaldo, HorarioEsperado, RutaOrigenDestino
from app.schemas.ingesta import ConfiguracionIngestaOut

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

    logger.info("Configuración entregada a %s: %s bases", agente.nombre, len(bases))
    return ConfiguracionIngestaOut(
        agente_id=agente.agente_id,
        agente_nombre=agente.nombre,
        generado_en=datetime.now(timezone.utc).isoformat(),
        bases=bases,
    )
