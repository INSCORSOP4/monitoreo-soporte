"""Acceso a datos: SQLAlchemy + pyodbc hacia MONITOREO_SOPORTE.

- Motor único creado al importar (reciclado de conexiones para VPN).
- `get_db()` como dependencia FastAPI (se abre/cierra la sesión por request).
- `Base` declarativa para los modelos (ORM).
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# pool_pre_ping: verifica la conexión antes de usarla (VPN puede caer, §6).
# pool_recycle: evita conexiones muertas por cortes prolongados de VPN.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Clase base para los modelos ORM (catálogos y operación)."""


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI que entrega una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
