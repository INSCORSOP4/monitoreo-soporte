"""NAS Transfer Worker (§11, §30) — mueve respaldos YA validados al NAS.

Flujo por item (exactamente el §11):
  1. Origen garantizado: solo recibe ejecuciones Estado=OK del checker
     (el backend las filtra; nunca transfiere respaldos no validados).
  2. Verifica que el destino (NAS) sea accesible — crea la carpeta si falta.
  3. Copia con shutil.copy2 (preserva fecha/mtime) a un nombre temporal .part
     y lo renombra al final: un .part colgado delata una copia incompleta
     (nunca queda un .bak a medias validable por el checker).
  4. Valida en destino (§12): tamaño idéntico y fecha (mtime) conservada
     SIEMPRE (rápido); SHA-256 completo opcional según HASH_VALIDACION.
  5. La eliminación del origen queda DIFERIDA (§30): transferir() devuelve
     eliminar_pendiente=True y solo el flujo de main() (tras confirmar
     COMPLETADA en el backend) llama a eliminar_origen(). En AGENT_DRY_RUN
     nunca elimina: registra 'HABRÍA ELIMINADO X'.
  6. Reporta la transferencia al backend (COMPLETADA/FALLIDA).

Regla crítica: si algo falla (NAS caído, hash distinto, copia incompleta),
el origen NO se toca y se reporta FALLIDA con detalle para intervención humana.
"""
import hashlib
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_PART_SUFIJO = ".part"  # marca de copia en curso en el destino
_TOLERANCIA_FECHA_SEG = 2  # copy2 conserva mtime; margen por FS de red


class TransferError(Exception):
    """Falla operativa de la transferencia (origen intacto, reportar FALLIDA)."""


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _human_bytes(n: int) -> str:
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.1f} {unidad}" if unidad != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


class NasTransferWorker:
    def __init__(
        self,
        origen_override: str = "",
        destino_override: str = "",
        dry_run: bool = True,
        validar_hash: bool = True,
    ):
        self._origen_override = origen_override.strip()
        self._destino_override = destino_override.strip()
        self.dry_run = dry_run
        self.validar_hash = validar_hash

    # ------------------------------------------------------------------ helpers

    def _ruta_origen(self, item: dict) -> Path:
        origen = Path(self._origen_override or item["ruta_origen"])
        return origen / item["archivo_encontrado"]

    def _ruta_destino(self, item: dict) -> Path:
        destino = Path(self._destino_override or item["ruta_destino"])
        return destino / item["archivo_encontrado"]

    @staticmethod
    def _verificar_destino(destino: Path) -> None:
        """§11 paso 2: NAS accesible (existe o se puede crear) y es carpeta."""
        try:
            if not destino.exists():
                destino.mkdir(parents=True)
            elif not destino.is_dir():
                raise TransferError(f"Destino no es una carpeta: {destino}")
        except TransferError:
            raise
        except OSError as exc:
            raise TransferError(f"NAS no accesible ({destino}): {exc}") from exc

    # ------------------------------------------------------------------- flujo

    def transferir(self, item: dict) -> dict:
        """Ejecuta el flujo §11 para un item. Devuelve el payload a reportar.

        Cualquier fallo deja el ORIGEN intacto (no se elimina nada) y el
        payload va con estado FALLIDA + error_detalle.
        """
        origen = self._ruta_origen(item)
        destino_archivo = self._ruta_destino(item)
        eliminar = bool(item.get("eliminar_origen_tras_transferencia", True))
        parte: Path | None = None  # se asigna tras verificar el destino

        try:
            # 1. El origen debe existir (lo reportó el checker; verificar igual).
            if not origen.is_file():
                raise TransferError(f"No existe el archivo origen: {origen}")

            # 2. NAS accesible.
            self._verificar_destino(destino_archivo.parent)

            # 3. Copia a .part y renombrado atómico al terminar.
            parte = destino_archivo.with_name(destino_archivo.name + _PART_SUFIJO)
            shutil.copy2(origen, parte)
            os.replace(parte, destino_archivo)

            # 4. Validación en destino (§12): tamaño + fecha + hash opcional.
            tam_origen = origen.stat().st_size
            tam_destino = destino_archivo.stat().st_size
            if tam_destino != tam_origen:
                raise TransferError(
                    f"Tamaño destino ({_human_bytes(tam_destino)}) != origen ({_human_bytes(tam_origen)})"
                )
            mtime_ok = abs(destino_archivo.stat().st_mtime - origen.stat().st_mtime) <= _TOLERANCIA_FECHA_SEG
            if not mtime_ok:
                raise TransferError("Fecha (mtime) no conservada en el destino")

            hash_origen = hash_destino = None
            hash_coincide = None
            if self.validar_hash:
                hash_origen = _sha256(origen)
                hash_destino = _sha256(destino_archivo)
                hash_coincide = hash_origen == hash_destino
                if not hash_coincide:
                    raise TransferError("Hash SHA-256 no coincide entre origen y destino (copia corrupta)")

            # 5. §30: la eliminación del origen se DIFIERE hasta que el backend
            #    confirme la transferencia (COMPLETADA + validación). Aquí solo
            #    se declara la intención; main() llama a eliminar_origen().
            eliminar_pendiente = False
            if eliminar:
                if self.dry_run:
                    logger.info("      DRY-RUN: HABRÍA ELIMINADO %s", origen)
                else:
                    eliminar_pendiente = True
                    logger.info("      Copia validada: eliminación del origen pendiente de confirmación del backend")
            else:
                logger.info("      Política del catálogo: conservar origen (%s)", origen)

            return {
                "ejecucion_id": item["ejecucion_id"],
                "base_datos_id": item["base_datos_id"],
                "estado": "COMPLETADA",
                "ruta_origen_efectiva": str(origen),
                "ruta_destino_efectiva": str(destino_archivo),
                "tamano_origen_bytes": tam_origen,
                "tamano_destino_bytes": tam_destino,
                "hash_origen": hash_origen,
                "hash_destino": hash_destino,
                "hash_coincide": hash_coincide,
                "origen_eliminado": False,
                "eliminar_pendiente": eliminar_pendiente,
                "error_detalle": None,
            }
        except TransferError as exc:
            self._limpiar_parte(parte)
            return self._fallida(item, str(exc))
        except OSError as exc:
            self._limpiar_parte(parte)
            return self._fallida(item, f"Error de sistema al transferir: {exc}")

    def eliminar_origen(self, item: dict) -> bool:
        """§30: elimina el origen SOLO después de que el backend confirmó la
        transferencia (COMPLETADA + validación aprobada). Nunca antes.

        Devuelve True si el origen ya no existe al terminar (eliminado por
        nosotros o ya ausente: el estado objetivo se alcanzó). False solo ante
        un error real (archivo en uso, permisos): se conserva y se reintenta
        en la siguiente corrida (solo_eliminar, §30 recuperación).
        """
        if self.dry_run:
            return False
        origen = self._ruta_origen(item)
        try:
            if not origen.exists():
                logger.info("      Origen ya no existe (nada que eliminar): %s", origen)
                return True
            origen.unlink()
            logger.info("      ELIMINADO origen tras confirmación del backend: %s", origen)
            return True
        except OSError as exc:
            logger.error("      NO se pudo eliminar el origen (%s): %s", origen, exc)
            return False

    def payload_eliminacion(self, item: dict, retry_number: int) -> dict:
        """Payload para marcar OrigenEliminado=1 en una transferencia ya COMPLETADA
        (§30 recuperación): el worker no re-copia, solo confirma el borrado.
        """
        origen = self._ruta_origen(item)
        destino = self._ruta_destino(item)
        return {
            "ejecucion_id": item["ejecucion_id"],
            "base_datos_id": item["base_datos_id"],
            "estado": "COMPLETADA",
            "ruta_origen_efectiva": str(origen),
            "ruta_destino_efectiva": str(destino),
            "tamano_origen_bytes": None,
            "tamano_destino_bytes": None,
            "hash_origen": None,
            "hash_destino": None,
            "hash_coincide": None,
            "origen_eliminado": not self.dry_run,  # en dry-run nada se elimina
            "error_detalle": None,
            "retry_number": retry_number,
        }

    def _fallida(self, item: dict, detalle: str) -> dict:
        """§30: ante cualquier fallo el origen se conserva y se reporta FALLIDA."""
        logger.error("      FALLIDA %s: %s", item["nombre_base"], detalle)
        return {
            "ejecucion_id": item["ejecucion_id"],
            "base_datos_id": item["base_datos_id"],
            "estado": "FALLIDA",
            "ruta_origen_efectiva": str(self._ruta_origen(item)),
            "ruta_destino_efectiva": str(self._ruta_destino(item)),
            "tamano_origen_bytes": None,
            "tamano_destino_bytes": None,
            "hash_origen": None,
            "hash_destino": None,
            "hash_coincide": None,
            "origen_eliminado": False,
            "eliminar_pendiente": False,
            "error_detalle": detalle,
        }

    @staticmethod
    def _limpiar_parte(parte: Path | None) -> None:
        """Un .part colgado se elimina: nunca debe quedar validable ni confundir."""
        if parte is None:
            return
        try:
            if parte.exists():
                parte.unlink()
        except OSError:
            logger.warning("No se pudo limpiar el archivo temporal %s", parte)
