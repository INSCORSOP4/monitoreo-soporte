"""Autenticación de AGENTES (máquinas) — §8.

Separada del JWT de humanos (get_current_user). Los endpoints de ingesta
usan esta dependencia, no HTTPBearer.

Flujo (formato de key '<AgenteId>.<secreto>', ej. "3.SxK9f..."):
  Header: X-Agent-Key: <key en claro>
  1. Leer la key del header y separar AgenteId.secreto (parse_api_key).
     Si el formato es inválido -> 401 INMEDIATO, sin tocar bcrypt.
  2. UN SOLO lookup por PK (AgenteId) en cat_agentes.
  3. UN SOLO bcrypt.verify del secreto contra ApiKeyHash + Activo = 1.

Al ser O(1) en lugar de O(n agentes), el costo de bcrypt solo se paga
cuando existe un agente con ese id: el riesgo de DoS por keys falsas
queda eliminado de raíz (antes se ejecutaba bcrypt contra CADA agente
activo por request).
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import parse_api_key, verify_api_key
from app.models import CatAgente

logger = get_logger(__name__)


def verify_agent_key(
    x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
    db: Session = Depends(get_db),
) -> CatAgente:
    """Valida la API key del agente (PK directa + un solo bcrypt) y Activo=1.

    Devuelve el CatAgente autenticado; lanza 401 si no es válido.
    """
    if not x_agent_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header X-Agent-Key requerido",
        )

    parsed = parse_api_key(x_agent_key)
    if parsed is None:
        logger.warning("X-Agent-Key con formato inválido (rechazada sin bcrypt)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key de agente inválida",
        )

    agente_id, secreto = parsed
    # UN SOLO lookup directo por PK (cat_agentes.AgenteId).
    agente = db.get(CatAgente, agente_id)
    if agente is None or not agente.activo or not verify_api_key(secreto, agente.api_key_hash):
        logger.warning("Autenticación de agente fallida (id=%s)", agente_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key de agente inválida",
        )

    logger.info("Agente autenticado: %s", agente.nombre)
    return agente
