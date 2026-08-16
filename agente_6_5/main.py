"""Agente — Backup Checker (Fase 4, §9/§10).

Ciclo:
  1. Lee su configuración del backend (GET /api/v1/ingesta/configuracion,
     autenticado con X-Agent-Key) — nada quemado en código (§35).
  2. Para cada base de las fuentes de ESTE agente (AGENT_TIPO_FUENTES del .env)
     valida la carpeta origen con el checker correspondiente del paquete
     checkers/ (cada proyecto trae SOLO sus checkers: SQL+Mongo en agente/,
     Microsip en agente_6_5/). El despacho es por tipo_fuente vía crear_checker().
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
from checkers import crear_checker
from config import AGENT_API_KEY, AGENT_FECHA, AGENT_ORIGEN_DIR, AGENT_TIPO_FUENTES, API_BASE_URL
from logger import get_logger

logger = get_logger(__name__)


def _fecha_operativa(arg_fecha: str | None) -> date:
    if arg_fecha:
        return date.fromisoformat(arg_fecha)
    if AGENT_FECHA:
        return date.fromisoformat(AGENT_FECHA)
    return date.today()


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente — Backup Checker (Fase 4, §9/§10)")
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
    logger.info("Backend: %s", API_BASE_URL)

    api = ApiClient(API_BASE_URL, AGENT_API_KEY)
    try:
        configuracion = api.get_configuracion()
    except ApiError as exc:
        logger.error("No se pudo obtener la configuración del backend: %s", exc)
        logger.error("Revise API_BASE_URL, AGENT_API_KEY y que el backend esté arriba.")
        return 2

    logger.info("AGENTE %s — Backup Checker | fecha operativa %s", configuracion["agente_nombre"], fecha.isoformat())

    # TODAS las bases SQL (aun con --solo) alimentan la resolución de colisiones
    # de prefijo del checker SQL (PROSUR_PRIME vs PROSUR_PRIME_DATA). En proyectos
    # sin SQL (agente_6_5) queda vacío y ningún checker lo usa.
    nombres_bases = tuple(b["nombre_base"] for b in configuracion["bases"] if b["tipo_fuente"] == "SQL")

    bases = configuracion["bases"]
    # Cada agente valida SOLO sus fuentes (AGENT_TIPO_FUENTES del .env, §35):
    # el 10.0.3.8 valida SQL,MONGO; el 192.168.6.5 valida MICROSIP,MERCALTOS.
    # Sin la variable (vacío) se validan todas las fuentes del catálogo.
    if AGENT_TIPO_FUENTES:
        bases = [b for b in bases if b["tipo_fuente"].upper() in AGENT_TIPO_FUENTES]
    if args.solo:
        bases = [b for b in bases if b["nombre_base"].lower() == args.solo.lower()]

    logger.info("Bases a validar: %s", ", ".join(b["nombre_base"] for b in bases) or "(ninguna)")

    conteo = {"OK": 0, "ADVERTENCIA": 0, "ERROR": 0, "NO_APLICA": 0}

    for base in bases:
        checker = crear_checker(
            base["tipo_fuente"],
            origen_override=args.origen or AGENT_ORIGEN_DIR,
            nombres_bases=nombres_bases,
        )
        if checker is None:
            logger.warning("Sin checker para %s — se omite %s", base["tipo_fuente"], base["nombre_base"])
            continue
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
