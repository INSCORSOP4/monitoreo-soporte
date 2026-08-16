"""Configuración del Agente 10.0.3.8 (§35: nada quemado en código).

Lee variables de entorno y un .env local (formato CLAVE=valor) SIN dependencias
externas. En 10.0.3.8 se configura vía Task Scheduler o variables del sistema.
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


# --- Conexión con el backend ---
API_BASE_URL = _env("API_BASE_URL", "http://localhost:8000").rstrip("/")
# Formato '<AgenteId>.<secreto>' — ver backend app/core/security.py
AGENT_API_KEY = _env("AGENT_API_KEY", "")

# --- Validación ---
# Override local de la carpeta origen (simulación). En 10.0.3.8 se deja VACÍO:
# el agente usa la RutaOrigen del catálogo del backend (G:\\TempRespSQLServer).
AGENT_ORIGEN_DIR = _env("AGENT_ORIGEN_DIR", "")
AGENT_FECHA = _env("AGENT_FECHA", "")  # override "YYYY-MM-DD" para pruebas
AGENT_MATCH_SUFIJOS = tuple(s for s in _env("AGENT_MATCH_SUFIJOS", ".bak,.BAK").split(",") if s)
# Fuentes que valida ESTE agente (coma-separada: SQL,MONGO,MICROSIP[,MERCALTOS]).
# Vacío = valida todas las fuentes que trae el catálogo. En 10.0.3.8:
# SQL,MONGO (Microsip/Mercaltos corren en el agente 6.5). En 192.168.6.5:
# MICROSIP,MERCALTOS. Mantener config.py IDÉNTICO entre agente/ y agente_6_5/.
AGENT_TIPO_FUENTES = tuple(s.strip().upper() for s in _env("AGENT_TIPO_FUENTES", "").split(",") if s.strip())

# --- Red (reintentos §13) ---
HTTP_TIMEOUT = int(_env("HTTP_TIMEOUT", "15"))
HTTP_RETRIES = int(_env("HTTP_RETRIES", "3"))
HTTP_RETRY_DELAY = int(_env("HTTP_RETRY_DELAY", "5"))

LOG_LEVEL = _env("LOG_LEVEL", "INFO")
