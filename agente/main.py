"""Agente 10.0.3.8 — Backup Checker SQL + Mongo (Fase 4, §9).

Ciclo:
  1. Lee su configuración del backend (GET /api/v1/ingesta/configuracion,
     autenticado con X-Agent-Key) — nada quemado en código (§35).
  2. Para cada base: valida la carpeta origen (existencia, tamaño, tipo,
     ventana horaria esperada). SQL valida archivos {Base}_{fecha}_{TIPO}.bak;
     Mongo valida dumps backup_YYYYMMDD_HHMM.rar (§9 Mongo).
  3. Reporta cada validación (POST /api/v1/respaldos/ejecuciones, idempotente).
     El backend crea la incidencia automática si el estado es ERROR (§26).

Uso:
  python main.py
  python main.py --fecha 2026-08-11          # fecha operativa explícita
  python main.py --origen C:\\temp\\sim       # override de carpeta (simulación)
  python main.py --solo PROSUR_PRIME         # solo una base
  python main.py --dry-run                   # valida sin reportar

Código de salida: 0 sin errores, 1 si hubo ERROR (útil para Task Scheduler).
"""
import argparse
import sys
from datetime import date

from api_client import ApiClient, ApiError
from checkers.mongo_backup import MongoBackupChecker
from checkers.sql_backup import SqlBackupChecker
from config import AGENT_API_KEY, AGENT_FECHA, AGENT_ORIGEN_DIR, API_BASE_URL
from logger import get_logger

logger = get_logger(__name__)


def _fecha_operativa(arg_fecha: str | None) -> date:
    if arg_fecha:
        return date.fromisoformat(arg_fecha)
    if AGENT_FECHA:
        return date.fromisoformat(AGENT_FECHA)
    return date.today()


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente 10.0.3.8 — Backup Checker SQL + Mongo")
    parser.add_argument("--fecha", help="Fecha operativa YYYY-MM-DD (defecto: hoy)")
    parser.add_argument("--origen", help="Override de la carpeta origen (simulación local)")
    parser.add_argument("--solo", help="Validar solo esta base (nombre exacto)")
    parser.add_argument("--dry-run", action="store_true", help="Valida sin reportar al backend")
    args = parser.parse_args()

    if not AGENT_API_KEY:
        logger.error("AGENT_API_KEY no está definida (revisar .env)")
        return 2

    fecha = _fecha_operativa(args.fecha)
    logger.info("=" * 62)
    logger.info("AGENTE 10.0.3.8 — Backup Checker SQL + Mongo | fecha operativa %s", fecha.isoformat())
    logger.info("Backend: %s", API_BASE_URL)

    api = ApiClient(API_BASE_URL, AGENT_API_KEY)
    try:
        configuracion = api.get_configuracion()
    except ApiError as exc:
        logger.error("No se pudo obtener la configuración del backend: %s", exc)
        logger.error("Revise API_BASE_URL, AGENT_API_KEY y que el backend esté arriba.")
        return 2

    # TODAS las bases SQL (aun con --solo) alimentan la resolución de colisiones
    # de prefijo del checker (PROSUR_PRIME vs PROSUR_PRIME_DATA).
    bases_sql = [b for b in configuracion["bases"] if b["tipo_fuente"] == "SQL"]
    bases_mongo = [b for b in configuracion["bases"] if b["tipo_fuente"] == "MONGO"]
    nombres_bases = tuple(b["nombre_base"] for b in bases_sql)

    bases = bases_sql + bases_mongo
    if args.solo:
        bases = [b for b in bases if b["nombre_base"].lower() == args.solo.lower()]

    logger.info("Bases a validar: %s", ", ".join(b["nombre_base"] for b in bases) or "(ninguna)")

    checker_sql = SqlBackupChecker(
        origen_override=args.origen or AGENT_ORIGEN_DIR,
        nombres_bases=nombres_bases,
    )
    checker_mongo = MongoBackupChecker(origen_override=args.origen or AGENT_ORIGEN_DIR)
    conteo = {"OK": 0, "ADVERTENCIA": 0, "ERROR": 0, "NO_APLICA": 0}

    for base in bases:
        checker = checker_mongo if base["tipo_fuente"] == "MONGO" else checker_sql
        payload = checker.check(base, fecha)
        logger.info("[%s] %s", payload["estado"], base["nombre_base"])
        if payload.get("detalle"):
            logger.info("      %s", payload["detalle"])

        if args.dry_run:
            continue

        try:
            resp = api.reportar_ejecucion(payload)
            logger.info(
                "      reportada: ejecucion_id=%s incidencia_id=%s",
                resp.get("ejecucion_id"),
                resp.get("incidencia_id"),
            )
        except Exception as exc:  # noqa: BLE001 — el ciclo sigue con las demás bases
            logger.error("      falló el reporte de %s: %s", base["nombre_base"], exc)
            continue
        conteo[payload["estado"]] += 1

    resumen = {k: v for k, v in conteo.items() if v}
    logger.info("=" * 62)
    logger.info("RESUMEN: %s", resumen if resumen else "(sin reportes)")
    errores = conteo["ERROR"]
    logger.info("Código de salida: %s (%s)", 1 if errores else 0, "hay ERRORES" if errores else "sin errores")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
