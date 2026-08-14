"""Cliente HTTP del agente hacia el backend — SOLO stdlib (urllib).

- TLS verificado por defecto cuando la URL es https:// (§38).
- Reintentos configurables en errores de red/5xx (§13); los 4xx no se reintentan.
- Header X-Agent-Key en cada request (autenticación de agente, §8).
"""
import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Error de comunicación con el backend (HTTP no-2xx o red)."""


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 15, retries: int = 3, retry_delay: int = 5):
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._retries = max(1, retries)
        self._retry_delay = retry_delay

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        cuerpo = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=cuerpo,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Agent-Key": self._api_key,
            },
        )
        ultimo_error: Exception | None = None
        for intento in range(1, self._retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    texto = resp.read().decode("utf-8")
                    return json.loads(texto) if texto else {}
            except urllib.error.HTTPError as exc:
                detalle = exc.read().decode("utf-8", errors="replace")
                if 400 <= exc.code < 500:
                    # Error del cliente (401/409/422...): reintentar no ayudaría.
                    raise ApiError(f"{method} {path} -> HTTP {exc.code}: {detalle}") from exc
                ultimo_error = ApiError(f"{method} {path} -> HTTP {exc.code}: {detalle}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                ultimo_error = ApiError(f"{method} {path} -> {exc}")
            if intento < self._retries:
                logger.warning(
                    "Reintento %s/%s en %ss tras: %s", intento, self._retries, self._retry_delay, ultimo_error
                )
                time.sleep(self._retry_delay)
        raise ultimo_error

    def get_configuracion(self) -> dict:
        """Catálogo completo (bases + rutas + horarios) — GET /ingesta/configuracion."""
        return self._request("GET", "/api/v1/ingesta/configuracion")

    def reportar_ejecucion(self, payload: dict) -> dict:
        """Reporta la validación de una base — POST /respaldos/ejecuciones (idempotente)."""
        return self._request("POST", "/api/v1/respaldos/ejecuciones", payload)
