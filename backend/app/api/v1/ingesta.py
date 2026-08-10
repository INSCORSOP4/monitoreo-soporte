"""Ingesta de AGENTES (§8, §24) — los agentes reportan al backend.

Autenticación: header X-Agent-Key (API key del agente, NO JWT de humano).
Los endpoints de ingesta usan verify_agent_key; el agente autenticado
se entrega como dependencia para registrar el reporte con su identidad.

Fase 4: aquí se agregarán los reportes reales (ejecuciones, transferencias).
Este router expone un endpoint mínimo para demostrar y validar el middleware.
"""
from fastapi import APIRouter, Depends

from app.api.deps_agent import verify_agent_key
from app.core.logging import get_logger
from app.models import CatAgente

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
