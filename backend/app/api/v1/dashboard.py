"""Dashboard — resumen general del día (§25)."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Incidencia, RespaldoEjecucion, ResponsableDia

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/resumen")
def resumen_dashboard(fecha: date, db: Session = Depends(get_db)) -> dict:
    """Indicadores de la sección 25 del plan."""
    responsable = db.scalar(
        select(ResponsableDia).where(ResponsableDia.fecha == fecha)
    )

    total_ejecuciones = db.scalar(
        select(func.count()).select_from(RespaldoEjecucion).where(RespaldoEjecucion.fecha_ejecucion == fecha)
    ) or 0
    ok_ejecuciones = db.scalar(
        select(func.count()).select_from(RespaldoEjecucion).where(
            RespaldoEjecucion.fecha_ejecucion == fecha,
            RespaldoEjecucion.estado == "OK",
        )
    ) or 0

    incidencias_abiertas = db.scalar(
        select(func.count()).select_from(Incidencia).where(
            Incidencia.fecha_incidencia == fecha,
            Incidencia.estado.in_(["ABIERTA", "EN_PROCESO"]),
        )
    ) or 0

    return {
        "fecha": fecha.isoformat(),
        "responsable_dia": responsable.usuario_id if responsable else None,
        "respaldos": {
            "total": total_ejecuciones,
            "ok": ok_ejecuciones,
            "porcentaje": round(ok_ejecuciones / total_ejecuciones * 100, 1) if total_ejecuciones else None,
        },
        "incidencias_abiertas": incidencias_abiertas,
    }
