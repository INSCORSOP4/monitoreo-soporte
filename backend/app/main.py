"""Aplicación FastAPI — MONITOREO_SOPORTE (Fase 3).

Inicio en desarrollo:
    python run.py

Documentación interactiva:
    http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("API iniciada — entorno: %s", settings.app_env)
    yield
    logger.info("API detenida")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API del Sistema de Monitoreo y Bitácora de Soporte (§32 Fase 3).",
    lifespan=lifespan,
)

# CORS — en producción se restringe a los orígenes configurados (§35)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
