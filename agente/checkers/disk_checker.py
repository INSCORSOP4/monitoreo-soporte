"""Disk Checker — espacio libre de las unidades del servidor (§33).

COMÚN a agente/ y agente_6_5/ (a diferencia de los checkers de respaldo, que
son específicos por agente): el disco se mide en la MÁQUINA donde corre el
agente, así que el mismo archivo sirve para ambos.

Descubrimiento DINÁMICO, no catálogo fijo:
  - ctypes.windll.kernel32.GetLogicalDrives() -> bitmask de unidades reales
    montadas (bit 0 = A:, bit 1 = B:, ...). Sin pip, solo stdlib.
  - shutil.disk_usage('X:\\\\') por cada unidad -> total/libre/porcentaje.

Los umbrales son GLOBALES (política igual para todas las unidades de todos los
servidores) y llegan del backend vía GET /ingesta/configuracion (§35):
  - disco_warning_pct (20) -> porcentaje libre < umbral => ADVERTENCIA
  - disco_error_pct   (10) -> porcentaje libre < umbral => ERROR

Cada unidad produce un payload listo para POST /discos/lecturas (idempotente
por ServidorId+Unidad+Fecha; el backend crea la incidencia SISTEMA si ERROR).

Estados:
  OK           -> porcentaje libre >= disco_warning_pct
  ADVERTENCIA  -> libre < disco_warning_pct (aún >= disco_error_pct)
  ERROR        -> libre < disco_error_pct, o unidad montada pero NO accesible
                  (ej. red caída / VPN / CD sin medio) — se reporta ERROR con
                  detalle específico, no se silencia.

El agente NO decide incidencias: reporta el hecho; el backend crea la
incidencia (§26).
"""
import ctypes
import shutil
from datetime import date

from logger import get_logger

logger = get_logger(__name__)


class DiskChecker:
    """Descubre las unidades reales del servidor y mide su espacio libre."""

    def __init__(
        self,
        servidor_id: int,
        umbral_warning_pct: float = 20.0,
        umbral_error_pct: float = 10.0,
        unidades_override: list[str] | None = None,
    ):
        self._servidor_id = servidor_id
        self._warning_pct = umbral_warning_pct
        self._error_pct = umbral_error_pct
        # Override para simulación local (probar estados sin unidades reales);
        # en producción se deja None y se descubren las unidades del servidor.
        self._unidades_override = unidades_override

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _normalizar_letra(letra: str) -> str:
        """'Z:', 'Z:\\' o 'Z' -> 'Z' (tolera el formato del override)."""
        return letra.rstrip(":\\").upper()

    @staticmethod
    def _descubrir_unidades() -> list[str]:
        """Unidades reales montadas vía GetLogicalDrives() (solo Windows).

        Devuelve ['C:', 'D:', ...] en orden alfabético. Si la llamada falla
        (bitmask 0), devuelve vacío: el check reportará que no hay unidades.
        """
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        except (AttributeError, OSError) as exc:  # noqa: BLE001 — no Windows
            logger.error("GetLogicalDrives() no disponible: %s", exc)
            return []
        letras = []
        for i in range(26):
            if bitmask & (1 << i):
                letras.append(chr(ord("A") + i))
        return letras

    @staticmethod
    def _estado_por_porcentaje(pct_libre: float, warning_pct: float, error_pct: float) -> str:
        """Clasifica el porcentaje libre contra los umbrales globales."""
        if pct_libre < error_pct:
            return "ERROR"
        if pct_libre < warning_pct:
            return "ADVERTENCIA"
        return "OK"

    def _leer_unidad(self, letra: str) -> dict:
        """Mide una unidad con shutil.disk_usage y construye el payload.

        Si la unidad está montada pero no responde (red caída, VPN, CD sin
        medio), devuelve un payload ERROR con detalle específico — una unidad
        que "existe pero no se puede leer" es un problema real, no se silencia.
        """
        raiz = f"{letra}:\\"
        try:
            uso = shutil.disk_usage(raiz)
        except OSError as exc:
            logger.warning("Unidad %s: no accesible (%s)", raiz, exc)
            return {
                "servidor_id": self._servidor_id,
                "unidad_letra": f"{letra}:",
                "fecha_lectura": "",
                "espacio_total_gb": None,
                "espacio_libre_gb": None,
                "porcentaje_libre": None,
                "estado": "ERROR",
                "detalle": f"Unidad {raiz} montada pero NO accesible: {exc}",
            }

        total_gb = uso.total / (1024**3)
        libre_gb = uso.free / (1024**3)
        pct = (uso.free / uso.total * 100) if uso.total else 0.0
        estado = self._estado_por_porcentaje(pct, self._warning_pct, self._error_pct)

        notas = []
        if estado == "ERROR":
            notas.append(f"libre < umbral de ERROR ({self._error_pct:.0f}%)")
        elif estado == "ADVERTENCIA":
            notas.append(f"libre < umbral de ADVERTENCIA ({self._warning_pct:.0f}%)")

        detalle = (
            f"Unidad {letra}: {libre_gb:,.2f} GB libres de {total_gb:,.2f} GB ({pct:.2f}%). "
            + (f"Notas: {'; '.join(notas)}." if notas else "Dentro de lo esperado.")
        )

        return {
            "servidor_id": self._servidor_id,
            "unidad_letra": f"{letra}:",
            "fecha_lectura": "",
            "espacio_total_gb": round(total_gb, 2),
            "espacio_libre_gb": round(libre_gb, 2),
            "porcentaje_libre": round(pct, 2),
            "estado": estado,
            "detalle": detalle,
        }

    # -------------------------------------------------------------------- check

    def check(self, fecha: date) -> list[dict]:
        """Payloads listos para POST /discos/lecturas, uno por unidad.

        Descubrimiento dinámico: si no hay override, se leen las unidades que
        GetLogicalDrives() reporta EN ESTE SERVIDOR (no un catálogo fijo).
        """
        if self._unidades_override is not None:
            letras = [self._normalizar_letra(u) for u in self._unidades_override]
            logger.info("Disk Checker con override de unidades: %s", ", ".join(letras) or "(ninguna)")
        else:
            letras = self._descubrir_unidades()
            logger.info("Disk Checker: unidades descubiertas %s", ", ".join(letras) or "(ninguna)")

        if not letras:
            return [{
                "servidor_id": self._servidor_id,
                "unidad_letra": "",
                "fecha_lectura": fecha.isoformat(),
                "espacio_total_gb": None,
                "espacio_libre_gb": None,
                "porcentaje_libre": None,
                "estado": "ERROR",
                "detalle": "No se detectaron unidades de disco en este servidor",
            }]

        payloads = []
        for letra in letras:
            payload = self._leer_unidad(letra)
            payload["fecha_lectura"] = fecha.isoformat()
            payloads.append(payload)
        return payloads
