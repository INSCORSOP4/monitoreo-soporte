"""Agregador de routers de la API v1 (§32 Fase 3 — módulos)."""
from fastapi import APIRouter

from app.api.v1 import (
    agentes,
    alertas,
    auth,
    bases_datos,
    dashboard,
    health,
    historial,
    incidencias,
    ingesta,
    respaldos,
    roles,
    servidores,
    usuarios,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(usuarios.router)
api_router.include_router(roles.router)
api_router.include_router(servidores.router)
api_router.include_router(agentes.router)
api_router.include_router(ingesta.router)
api_router.include_router(bases_datos.router)
api_router.include_router(respaldos.router)
api_router.include_router(incidencias.router)
api_router.include_router(alertas.router)
api_router.include_router(historial.router)
api_router.include_router(dashboard.router)
