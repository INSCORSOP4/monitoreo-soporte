"""Configuración del NAS Transfer Worker (§11, §30 — nada quemado en código).

Lee variables de entorno y un .env local (formato CLAVE=valor) SIN dependencias
externas. En 10.0.3.8 se configura vía Task Scheduler o variables del sistema.

Diferencias clave con el checker SQL:
  AGENT_DRY_RUN=true  -> copia y valida como si fuera real, pero NUNCA elimina
                         el origen: registra 'HABRÍA ELIMINADO X' (§30). Es el
                         modo predeterminado de despliegue inicial.
  AGENT_DESTINO_DIR   -> override local del destino (simulación de NAS). Vacío
                         en producción: se usa la RutaDestino del catálogo.
  AGENT_SSL_CA_BUNDLE -> .pem del certificado raíz interno si el backend usa
                         HTTPS autofirmado (urllib verifica TLS por defecto).
"""
import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _cargar_env() -> None:
    archivo = _DIR / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env()


def _env(clave: str, default: str = "") -> str:
    return os.environ.get(clave, default).strip()


def _env_bool(clave: str, default: bool) -> bool:
    valor = _env(clave, "true" if default else "false").lower()
    return valor in ("1", "true", "yes", "on")


# --- Conexión con el backend ---
API_BASE_URL = _env("API_BASE_URL", "http://localhost:8000").rstrip("/")
# Formato '<AgenteId>.<secreto>' — ver backend app/core/security.py
AGENT_API_KEY = _env("AGENT_API_KEY", "")

# --- Transferencia ---
# Overrides locales de simulación. Vacíos en producción: el worker usa las
# rutas del catálogo del backend (rutas_origen_destino, §5 rutas estrictas).
AGENT_ORIGEN_DIR = _env("AGENT_ORIGEN_DIR", "")
AGENT_DESTINO_DIR = _env("AGENT_DESTINO_DIR", "")
AGENT_FECHA = _env("AGENT_FECHA", "")  # override "YYYY-MM-DD" para pruebas

# MODO SEGURO: copia y valida de verdad, pero NO elimina el origen (§30).
AGENT_DRY_RUN = _env_bool("AGENT_DRY_RUN", True)

# Validación de integridad en destino (§12): tamaño + fecha (mtime) SIEMPRE.
# El SHA-256 completo es OPCIONAL: en Fulls de >8 GB cuesta tiempo de cómputo,
# por eso HASH_VALIDACION=false es el flujo normal rápido. true = la capa extra
# de integridad para cuando se requiera, sin cambiar el flujo.
HASH_VALIDACION = _env_bool("HASH_VALIDACION", False)

# --- Reintentos de transferencia (§13) ---
# Por item: hasta TRANSFER_RETRIES intentos con espera entre cada uno (nunca
# infinito). Cada intento fallido queda registrado en transferencias (FALLIDA).
TRANSFER_RETRIES = max(1, int(_env("TRANSFER_RETRIES", "3")))
TRANSFER_RETRY_DELAY = max(0, int(_env("TRANSFER_RETRY_DELAY", "30")))

# TLS: .pem del certificado raíz interno para HTTPS autofirmado (§38).
AGENT_SSL_CA_BUNDLE = _env("AGENT_SSL_CA_BUNDLE", "")

# --- Red HTTP (reintentos §13) ---
HTTP_TIMEOUT = int(_env("HTTP_TIMEOUT", "15"))
HTTP_RETRIES = int(_env("HTTP_RETRIES", "3"))
HTTP_RETRY_DELAY = int(_env("HTTP_RETRY_DELAY", "5"))

LOG_LEVEL = _env("LOG_LEVEL", "INFO")
