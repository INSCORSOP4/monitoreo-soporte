"""Configuración común de agentes (§35: nada quemado en código).

Lee variables de entorno y un .env local (formato CLAVE=valor) SIN dependencias
externas. En producción se configura vía Task Scheduler o variables del sistema.
"""
import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _cargar_env() -> None:
    for archivo in (_DIR / ".env", _DIR / ".env.sql-jobs"):
        if not archivo.exists():
            continue
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
# Override local de la carpeta origen (simulación). En producción se deja VACÍO:
# el agente usa la RutaOrigen del catálogo del backend.
AGENT_ORIGEN_DIR = _env("AGENT_ORIGEN_DIR", "")
AGENT_FECHA = _env("AGENT_FECHA", "")  # override "YYYY-MM-DD" para pruebas
AGENT_MATCH_SUFIJOS = tuple(s for s in _env("AGENT_MATCH_SUFIJOS", ".bak,.BAK").split(",") if s)
# Fuentes que valida ESTE agente (coma-separada: SQL,MONGO,MICROSIP[,MERCALTOS]).
# Vacío = valida todas las fuentes que trae el catálogo. En 10.0.3.8:
# SQL,MONGO (Microsip/Mercaltos corren en el agente 6.5). En 192.168.6.5:
# MICROSIP,MERCALTOS. Mantener config.py IDÉNTICO entre agente/ y agente_6_5/.
AGENT_TIPO_FUENTES = tuple(s.strip().upper() for s in _env("AGENT_TIPO_FUENTES", "").split(",") if s.strip())

# --- SQL Server Agent (solo se usa en agentes que monitorean SQL Agent) ---
# localhost = el agente corre en el mismo servidor SQL; usar IP/instancia cuando
# el agente deba consultar una instancia remota.
SQL_JOBS_SERVER = _env("SQL_JOBS_SERVER", "localhost")
SQL_JOBS_USER = _env("SQL_JOBS_USER", "")
SQL_JOBS_PASSWORD = _env("SQL_JOBS_PASSWORD", "")

# --- Red (reintentos §13) ---
HTTP_TIMEOUT = int(_env("HTTP_TIMEOUT", "15"))
HTTP_RETRIES = int(_env("HTTP_RETRIES", "3"))
HTTP_RETRY_DELAY = int(_env("HTTP_RETRY_DELAY", "5"))

LOG_LEVEL = _env("LOG_LEVEL", "INFO")
