"""NAS Transfer Worker (§11, §30) — copia al NAS los respaldos YA validados.

Ciclo:
  1. Pide al backend las ejecuciones OK sin transferencia COMPLETADA
     (GET /ingesta/pendientes-transferir, autenticado con X-Agent-Key).
  2. Por cada item: verificar NAS -> copiar -> validar (tamaño/fecha siempre,
     hash según HASH_VALIDACION) -> reportar COMPLETADA -> solo entonces
     eliminar origen (§30). Reintentos limitados con espera (§13); cada
     intento fallido queda registrado como FALLIDA. En AGENT_DRY_RUN nunca
     elimina.
  3. Reporta cada resultado (POST /transferencias, idempotente por retry).
     El backend rechaza registrar OrigenEliminado sin COMPLETADA validada (§30).

Código de salida (para Task Scheduler y alertas):
  0  -> el worker funcionó y no hubo fallos (todo COMPLETADA / nada pendiente).
  1  -> el worker funcionó y encontró un problema REAL (transferencias FALLIDA):
        alertar a Soporte — hay respaldos sin llegar al NAS.
  2  -> el worker FALLÓ él mismo (backend inaccesible, config inválida):
        alertar como falla del sistema de monitoreo, NO como problema de respaldo.

Uso:
  python main.py
  python main.py --fecha 2026-08-11          # fecha operativa explícita
  python main.py --origen C:\\temp\\sim --destino C:\\temp\\nas_sim
  python main.py --no-dry-run                # override puntual del .env
"""
import argparse
import sys
import time
from datetime import date

from api_client import ApiClient, ApiError
from config import (
    AGENT_API_KEY,
    AGENT_DESTINO_DIR,
    AGENT_DRY_RUN,
    AGENT_FECHA,
    AGENT_ORIGEN_DIR,
    AGENT_SSL_CA_BUNDLE,
    API_BASE_URL,
    HASH_VALIDACION,
    HTTP_RETRIES,
    HTTP_RETRY_DELAY,
    HTTP_TIMEOUT,
    TRANSFER_RETRIES,
    TRANSFER_RETRY_DELAY,
)
from logger import get_logger
from worker import NasTransferWorker

logger = get_logger(__name__)


def _fecha_operativa(arg_fecha: str | None) -> date:
    if arg_fecha:
        return date.fromisoformat(arg_fecha)
    if AGENT_FECHA:
        return date.fromisoformat(AGENT_FECHA)
    return date.today()


def _transferir_con_reintentos(
    worker: NasTransferWorker,
    api: ApiClient,
    item: dict,
    reintentos: int,
    espera_seg: int,
) -> tuple[str, dict | None, dict]:
    """§13: transfiere un item con reintentos LIMITADOS y espera (nunca infinito).

    Cada intento se registra en el backend: si falla queda como FALLIDA (el
    origen NO se toca, §30) y se reintenta tras la espera. Solo cuando el
    backend confirma COMPLETADA se elimina el origen y se actualiza el
    registro con OrigenEliminado=1 (§30: nunca copiar->eliminar).

    Devuelve (estado_final, respuesta_final, payload_final).
    """
    previa = item.get("transferencia_existente")
    # RetryNumber es TINYINT en la BD (máx 255): se topa para que la reintento
    # entre corridas nunca desborde y quede reportando 422 para siempre.
    base_retry = min((previa["retry_number"] if previa else 0), 255 - reintentos)
    ultima_resp: dict | None = None
    ultimo_payload: dict = {}

    for intento in range(1, reintentos + 1):
        payload = worker.transferir(item)
        payload["retry_number"] = base_retry + intento
        eliminar_pendiente = bool(payload.pop("eliminar_pendiente", False))
        ultimo_payload = payload

        try:
            resp = api.reportar_transferencia(payload)
        except ApiError as exc:
            logger.error("      no se pudo registrar intento %s de %s: %s",
                         base_retry + intento, item["nombre_base"], exc)
            if intento < reintentos:
                time.sleep(espera_seg)
                continue
            payload["error_detalle"] = f"no se pudo registrar en el backend: {exc}"
            return "FALLIDA", None, payload

        ultima_resp = resp
        if resp.get("estado") == "COMPLETADA":
            # §30: el backend confirmó; solo ahora se toca el origen.
            if eliminar_pendiente:
                if worker.eliminar_origen(item):
                    payload["origen_eliminado"] = True
                    try:
                        resp = api.reportar_transferencia(payload)  # upsert: OrigenEliminado=1
                        ultima_resp = resp
                    except ApiError as exc:
                        logger.error("      copia confirmada, pero no se pudo marcar OrigenEliminado=1: %s", exc)
                else:
                    # El origen NO se pudo eliminar (archivo en uso, permisos...):
                    # la transferencia quedó COMPLETADA; la próxima corrida la
                    # recibe con solo_eliminar=True y reintenta el borrado (§30).
                    payload["pendiente_eliminar"] = True
                    logger.error("      copia confirmada pero NO se pudo eliminar el origen (%s): reintento en la próxima corrida",
                                 worker._ruta_origen(item))
            return "COMPLETADA", resp, payload

        # FALLIDA (el origen quedó intacto, §30): reintentar si quedan intentos.
        if intento < reintentos:
            logger.warning(
                "      %s: intento %s/%s FALLIDA (%s); reintento en %ss",
                item["nombre_base"], intento, reintentos,
                payload.get("error_detalle"), espera_seg,
            )
            time.sleep(espera_seg)

    return "FALLIDA", ultima_resp, ultimo_payload


def _eliminar_solo_con_reintentos(
    worker: NasTransferWorker,
    api: ApiClient,
    item: dict,
    reintentos: int,
    espera_seg: int,
) -> tuple[str, dict | None, dict]:
    """§30 recuperación: la transferencia ya quedó COMPLETADA en una corrida
    previa pero el origen no se pudo eliminar (archivo en uso, permisos...).
    Reintenta SOLO el borrado (sin re-copiar) y marca OrigenEliminado=1.

    Devuelve (estado_final, respuesta_final, payload_final).
    """
    previa = item.get("transferencia_existente")
    retry = previa["retry_number"] if previa else 1
    origen = worker._ruta_origen(item)
    logger.info("[%s] solo_eliminar (recuperación §30): %s", item["nombre_base"], origen)

    if worker.dry_run:
        logger.info("      DRY-RUN: HABRÍA ELIMINADO %s (recuperación)", origen)
        return "COMPLETADA", None, worker.payload_eliminacion(item, retry)

    for intento in range(1, reintentos + 1):
        if worker.eliminar_origen(item):
            payload = worker.payload_eliminacion(item, retry)
            try:
                resp = api.reportar_transferencia(payload)  # upsert sobre la COMPLETADA original
                logger.info("      OrigenEliminado=1 confirmado (recuperación, intento %s)", intento)
                return "COMPLETADA", resp, payload
            except ApiError as exc:
                logger.error("      origen eliminado pero no se pudo marcar OrigenEliminado=1: %s", exc)
                return "FALLIDA", None, payload
        if intento < reintentos:
            logger.warning("      reintento %s/%s de eliminación (%s): %s", intento, reintentos,
                           item["nombre_base"], origen)
            time.sleep(espera_seg)

    logger.error("      NO se pudo eliminar el origen (%s) tras %s intentos: requiere intervención",
                 origen, reintentos)
    return "FALLIDA", None, worker.payload_eliminacion(item, retry)


def main() -> int:
    parser = argparse.ArgumentParser(description="NAS Transfer Worker — SQL -> NAS (§11)")
    parser.add_argument("--fecha", help="Fecha operativa YYYY-MM-DD (defecto: hoy)")
    parser.add_argument("--solo", help="Transferir solo esta base (nombre exacto)")
    parser.add_argument("--origen", help="Override de la carpeta origen (simulación)")
    parser.add_argument("--destino", help="Override del destino NAS (simulación)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=None, help="No eliminar origen")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Eliminar origen al confirmar")
    args = parser.parse_args()

    if not AGENT_API_KEY:
        logger.error("AGENT_API_KEY no está definida (revisar .env)")
        return 2

    dry_run = AGENT_DRY_RUN if args.dry_run is None else args.dry_run
    fecha = _fecha_operativa(args.fecha)
    logger.info("=" * 62)
    logger.info("NAS TRANSFER WORKER | fecha operativa %s", fecha.isoformat())
    logger.info("Backend: %s | modo: %s | hash: %s",
                API_BASE_URL, "DRY-RUN (no elimina)" if dry_run else "REAL (elimina al confirmar)",
                "on" if HASH_VALIDACION else "off")
    if dry_run:
        logger.warning("*** MODO DRY-RUN: se copiará y validará, pero NINGÚN archivo origen será eliminado ***")

    api = ApiClient(API_BASE_URL, AGENT_API_KEY, HTTP_TIMEOUT, HTTP_RETRIES, HTTP_RETRY_DELAY, AGENT_SSL_CA_BUNDLE)
    try:
        pendientes = api.get_pendientes(fecha.isoformat())
    except ApiError as exc:
        logger.error("No se pudo obtener los pendientes del backend: %s", exc)
        logger.error("Revise API_BASE_URL, AGENT_API_KEY y que el backend esté arriba.")
        return 2

    items = pendientes.get("items", [])
    if args.solo:
        items = [i for i in items if i["nombre_base"].lower() == args.solo.lower()]
    if not items:
        logger.info("Sin ejecuciones OK pendientes de transferir para %s. Nada que hacer.", fecha)
        return 0

    logger.info("Pendientes: %s", ", ".join(i["nombre_base"] for i in items))
    worker = NasTransferWorker(
        origen_override=args.origen or AGENT_ORIGEN_DIR,
        destino_override=args.destino or AGENT_DESTINO_DIR,
        dry_run=dry_run,
        validar_hash=HASH_VALIDACION,
    )

    completadas = 0
    fallidas = 0
    for item in items:
        logger.info("[%s] %s -> %s", item["nombre_base"], item["archivo_encontrado"],
                    worker._ruta_destino(item).parent)

        if item.get("solo_eliminar"):
            estado, resp, payload = _eliminar_solo_con_reintentos(
                worker, api, item, TRANSFER_RETRIES, TRANSFER_RETRY_DELAY
            )
        else:
            estado, resp, payload = _transferir_con_reintentos(
                worker, api, item, TRANSFER_RETRIES, TRANSFER_RETRY_DELAY
            )

        if estado == "COMPLETADA":
            completadas += 1
            if payload.get("pendiente_eliminar"):
                fallidas += 1
                logger.error(
                    "      %s: transferencia COMPLETADA pero origen pendiente de eliminar "
                    "(reintento en la próxima corrida, §30)", item["nombre_base"])
            else:
                logger.info(
                    "      COMPLETADA (transferencia_id=%s, %s, hash=%s, origen_eliminado=%s)",
                    (resp or {}).get("transferencia_id"),
                    _human_bytes(payload.get("tamano_destino_bytes") or 0),
                    "coincide" if payload.get("hash_coincide") else ("n/d" if payload.get("hash_origen") is None else "NO"),
                    payload.get("origen_eliminado"),
                )
        else:
            fallidas += 1
            logger.info("      %s (transferencia_id=%s): %s", estado,
                        (resp or {}).get("transferencia_id") if resp else "-",
                        payload.get("error_detalle"))

    logger.info("=" * 62)
    logger.info("RESUMEN: COMPLETADAS=%s FALLIDAS=%s (modo %s)",
                completadas, fallidas, "DRY-RUN" if dry_run else "REAL")
    if fallidas:
        logger.info("Código de salida: 1 (el worker funcionó; hay respaldos que no llegaron al NAS)")
        return 1
    logger.info("Código de salida: 0 (sin fallos)")
    return 0


def _human_bytes(n: int) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.1f} {unidad}" if unidad != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


if __name__ == "__main__":
    sys.exit(main())
