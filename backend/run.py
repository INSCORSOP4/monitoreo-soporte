"""Punto de entrada del backend MONITOREO_SOPORTE.

Uso (desde monitoreo-soporte/backend):
    pip install -r requirements.txt
    python run.py

Configuración: variables de entorno en .env (§35, sin credenciales en código).
"""
import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    # Enforcement de TLS (§38): en PRODUCCIÓN el servicio NO arranca sin HTTPS.
    # La VPN cifra entre redes, pero dentro de la red la X-Agent-Key viajaría en
    # claro sin TLS — el requisito se vuelve barrera, no documentación.
    if settings.is_production and not (settings.ssl_certfile and settings.ssl_keyfile):
        raise SystemExit(
            "APP_ENV=production requiere TLS: define SSL_CERTFILE y SSL_KEYFILE en .env "
            "(la X-Agent-Key de los agentes viajaría en claro sin HTTPS)."
        )

    # TLS (§38): si SSL_CERTFILE y SSL_KEYFILE están definidos en .env, uvicorn
    # sirve HTTPS. En desarrollo (solo VPN/loopback) pueden quedar vacíos.
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        ssl_certfile=settings.ssl_certfile or None,
        ssl_keyfile=settings.ssl_keyfile or None,
    )
