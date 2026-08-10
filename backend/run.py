"""Punto de entrada del backend MONITOREO_SOPORTE.

Uso (desde monitoreo-soporte/backend):
    pip install -r requirements.txt
    python run.py

Configuración: variables de entorno en .env (§35, sin credenciales en código).
"""
import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
