"""Health — estado de la API y conectividad con la base de datos."""
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — reportamos el estado, no la excepción
        logger.error("Health check BD fallido: %s", exc)
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degradado",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
