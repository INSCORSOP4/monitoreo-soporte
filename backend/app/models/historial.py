"""Modelo ORM — Historial de auditoría (§27, §35: trazabilidad)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Historial(Base):
    __tablename__ = "historial"

    historial_id: Mapped[int] = mapped_column("HistorialId", BigInteger, primary_key=True, autoincrement=True)
    fecha_evento: Mapped[datetime] = mapped_column("FechaEvento", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
    usuario_id: Mapped[int | None] = mapped_column("UsuarioId", Integer, ForeignKey("cat_usuarios.UsuarioId"))
    entidad: Mapped[str] = mapped_column("Entidad", String(80), nullable=False)
    entidad_id: Mapped[int | None] = mapped_column("EntidadId", Integer)
    tipo_evento: Mapped[str] = mapped_column("TipoEvento", String(20), nullable=False)
    datos_antes: Mapped[str | None] = mapped_column("DatosAntes", Text)
    datos_despues: Mapped[str | None] = mapped_column("DatosDespues", Text)
    descripcion: Mapped[str | None] = mapped_column("Descripcion", String(500))
