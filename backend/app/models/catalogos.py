"""Modelos ORM — Catálogos (esquema dbo, secciones 1.1 a 1.6 del DDL)."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CatRol(Base):
    __tablename__ = "cat_roles"

    rol_id: Mapped[int] = mapped_column("RolId", Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column("Codigo", String(20), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column("Nombre", String(60), nullable=False)
    descripcion: Mapped[str | None] = mapped_column("Descripcion", String(255))
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class CatUsuario(Base):
    __tablename__ = "cat_usuarios"

    usuario_id: Mapped[int] = mapped_column("UsuarioId", Integer, primary_key=True, autoincrement=True)
    # Opcional: referencia lógica a SEGURIDAD_PROSUR; NULL para usuarios creados localmente.
    usuario_externo_id: Mapped[int | None] = mapped_column("UsuarioExternoId", Integer, nullable=True)
    nombre_completo: Mapped[str] = mapped_column("NombreCompleto", String(120), nullable=False)
    correo: Mapped[str] = mapped_column("Correo", String(120), nullable=False, unique=True)  # identificador de login
    rol_id: Mapped[int] = mapped_column("RolId", Integer, ForeignKey("cat_roles.RolId"), nullable=False)
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    password_hash: Mapped[str | None] = mapped_column("PasswordHash", String(255))  # hash bcrypt, nunca en claro
    debe_cambiar_password: Mapped[bool] = mapped_column("DebeCambiarPassword", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class CatServidor(Base):
    __tablename__ = "cat_servidores"

    servidor_id: Mapped[int] = mapped_column("ServidorId", Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column("Nombre", String(50), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column("Descripcion", String(255))
    tipo_servidor: Mapped[str] = mapped_column("TipoServidor", String(20), nullable=False)
    es_nas: Mapped[bool] = mapped_column("EsNAS", Boolean, nullable=False, server_default="0")
    es_origen_respaldo: Mapped[bool] = mapped_column("EsOrigenRespaldo", Boolean, nullable=False, server_default="0")
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class CatGrupoRespaldo(Base):
    __tablename__ = "cat_grupos_respaldo"

    grupo_respaldo_id: Mapped[int] = mapped_column("GrupoRespaldoId", Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column("Codigo", String(30), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column("Nombre", String(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column("Descripcion", String(255))
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False)


class CatBaseDatos(Base):
    __tablename__ = "cat_bases_datos"

    base_datos_id: Mapped[int] = mapped_column("BaseDatosId", Integer, primary_key=True, autoincrement=True)
    grupo_respaldo_id: Mapped[int] = mapped_column("GrupoRespaldoId", Integer, ForeignKey("cat_grupos_respaldo.GrupoRespaldoId"), nullable=False)
    servidor_origen_id: Mapped[int | None] = mapped_column("ServidorOrigenId", Integer, ForeignKey("cat_servidores.ServidorId"))
    nombre_base: Mapped[str] = mapped_column("NombreBase", String(120), nullable=False)
    tipo_fuente: Mapped[str] = mapped_column("TipoFuente", String(20), nullable=False)
    tipo_backup_predeterminado: Mapped[str] = mapped_column("TipoBackupPredeterminado", String(15), nullable=False)
    observaciones: Mapped[str | None] = mapped_column("Observaciones", String(255))
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class CatTipoIncidencia(Base):
    __tablename__ = "cat_tipos_incidencia"

    tipo_incidencia_id: Mapped[int] = mapped_column("TipoIncidenciaId", Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column("Codigo", String(40), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column("Nombre", String(80), nullable=False)
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")


class CatAgente(Base):
    """Agente (máquina) que reporta al backend (§8). No es una persona."""

    __tablename__ = "cat_agentes"

    agente_id: Mapped[int] = mapped_column("AgenteId", Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column("Nombre", String(50), nullable=False, unique=True)
    api_key_hash: Mapped[str] = mapped_column("ApiKeyHash", String(255), nullable=False)  # hash bcrypt, nunca en claro
    servidor_id: Mapped[int | None] = mapped_column("ServidorId", Integer, ForeignKey("cat_servidores.ServidorId"))  # §33: servidor donde corre el agente
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
