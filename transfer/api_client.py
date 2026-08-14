"""Cliente HTTP del NAS Transfer Worker hacia el backend — SOLO stdlib (urllib).

- TLS verificado por defecto cuando la URL es https:// (§38). Si el backend
  usa un certificado autofirmado interno, AGENT_SSL_CA_BUNDLE apunta al .pem
  de la CA raíz y se usa como origen de confianza.
- Reintentos configurables en errores de red/5xx (§13); los 4xx no se reintentan.
- Header X-Agent-Key en cada request (autenticación de agente, §8).
"""
import json
import logging
import ssl
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Error de comunicación con el backend (HTTP no-2xx o red)."""


class ApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 15,
        retries: int = 3,
        retry_delay: int = 5,
        ca_bundle: str = "",
    ):
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._retries = max(1, retries)
        self._retry_delay = retry_delay
        self._contexto = self._contexto_ssl(ca_bundle)

    @staticmethod
    def _contexto_ssl(ca_bundle: str):
        """Contexto TLS con CA interna si se configuró AGENT_SSL_CA_BUNDLE.

        urllib ya verifica certificados contra las CA públicas por defecto;
        este bundle solo añade la CA raíz interna (certificados autofirmados
        del entorno de la empresa) a las de confianza.
        """
        if not ca_bundle:
            return None
        return ssl.create_default_context(cafile=ca_bundle)

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
                with urllib.request.urlopen(req, timeout=self._timeout, context=self._contexto) as resp:
                    texto = resp.read().decode("utf-8")
                    return json.loads(texto) if texto else {}
            except urllib.error.HTTPError as exc:
                detalle = exc.read().decode("utf-8", errors="replace")
                if 400 <= exc.code < 500:
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

    def get_pendientes(self, fecha: str) -> dict:
        """Ejecuciones OK sin transferencia COMPLETADA — GET /ingesta/pendientes-transferir."""
        return self._request("GET", f"/api/v1/ingesta/pendientes-transferir?fecha={fecha}")

    def reportar_transferencia(self, payload: dict) -> dict:
        """Registra el resultado de una transferencia — POST /transferencias (idempotente)."""
        return self._request("POST", "/api/v1/transferencias", payload)
