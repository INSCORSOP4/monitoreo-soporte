"""Modelos ORM — Operación diaria (secciones 3.1 a 3.7 del DDL)."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RespaldoEjecucion(Base):
    __tablename__ = "respaldos_ejecuciones"

    ejecucion_id: Mapped[int] = mapped_column("EjecucionId", BigInteger, primary_key=True, autoincrement=True)
    base_datos_id: Mapped[int] = mapped_column("BaseDatosId", Integer, ForeignKey("cat_bases_datos.BaseDatosId"), nullable=False)
    fecha_ejecucion: Mapped[date] = mapped_column("FechaEjecucion", Date, nullable=False)
    estado: Mapped[str] = mapped_column("Estado", String(15), nullable=False)  # OK/ADVERTENCIA/ERROR/PENDIENTE/NO_APLICA
    tipo_backup_encontrado: Mapped[str | None] = mapped_column("TipoBackupEncontrado", String(15))
    archivo_encontrado: Mapped[str | None] = mapped_column("ArchivoEncontrado", String(500))
    tamano_bytes: Mapped[int | None] = mapped_column("TamanoBytes", BigInteger)
    fecha_generacion: Mapped[datetime | None] = mapped_column("FechaGeneracion", DateTime(0))
    fuera_de_horario: Mapped[bool | None] = mapped_column("FueraDeHorario", Boolean)
    detalle: Mapped[str | None] = mapped_column("Detalle", Text)
    incidencia_id: Mapped[int | None] = mapped_column("IncidenciaId", Integer)
    usuario_reviso_id: Mapped[int | None] = mapped_column("UsuarioRevisoId", Integer, ForeignKey("cat_usuarios.UsuarioId"))
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class Transferencia(Base):
    __tablename__ = "transferencias"

    transferencia_id: Mapped[int] = mapped_column("TransferenciaId", BigInteger, primary_key=True, autoincrement=True)
    ejecucion_id: Mapped[int] = mapped_column("EjecucionId", BigInteger, ForeignKey("respaldos_ejecuciones.EjecucionId"), nullable=False)
    base_datos_id: Mapped[int] = mapped_column("BaseDatosId", Integer, ForeignKey("cat_bases_datos.BaseDatosId"), nullable=False)
    fecha_transferencia: Mapped[datetime] = mapped_column("FechaTransferencia", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
    retry_number: Mapped[int] = mapped_column("RetryNumber", Integer, nullable=False, server_default="1")
    estado: Mapped[str] = mapped_column("Estado", String(20), nullable=False)  # EN_PROGRESO/COMPLETADA/FALLIDA/PENDIENTE
    ruta_origen_efectiva: Mapped[str] = mapped_column("RutaOrigenEfectiva", String(500), nullable=False)
    ruta_destino_efectiva: Mapped[str] = mapped_column("RutaDestinoEfectiva", String(500), nullable=False)
    tamano_origen_bytes: Mapped[int | None] = mapped_column("TamanoOrigenBytes", BigInteger)
    tamano_destino_bytes: Mapped[int | None] = mapped_column("TamanoDestinoBytes", BigInteger)
    hash_origen: Mapped[str | None] = mapped_column("HashOrigen", String(64))
    hash_destino: Mapped[str | None] = mapped_column("HashDestino", String(64))
    hash_coincide: Mapped[bool | None] = mapped_column("HashCoincide", Boolean)
    origen_eliminado: Mapped[bool] = mapped_column("OrigenEliminado", Boolean, nullable=False, server_default="0")  # §30
    error_detalle: Mapped[str | None] = mapped_column("ErrorDetalle", Text)
    incidencia_id: Mapped[int | None] = mapped_column("IncidenciaId", Integer)
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class Incidencia(Base):
    __tablename__ = "incidencias"

    incidencia_id: Mapped[int] = mapped_column("IncidenciaId", Integer, primary_key=True, autoincrement=True)
    tipo_incidencia_id: Mapped[int] = mapped_column("TipoIncidenciaId", Integer, ForeignKey("cat_tipos_incidencia.TipoIncidenciaId"), nullable=False)
    servidor_id: Mapped[int | None] = mapped_column("ServidorId", Integer, ForeignKey("cat_servidores.ServidorId"))
    base_datos_id: Mapped[int | None] = mapped_column("BaseDatosId", Integer, ForeignKey("cat_bases_datos.BaseDatosId"))
    fecha_incidencia: Mapped[date] = mapped_column("FechaIncidencia", Date, nullable=False)
    estado: Mapped[str] = mapped_column("Estado", String(15), nullable=False, server_default="ABIERTA")
    detectada_por: Mapped[str] = mapped_column("DetectadaPor", String(10), nullable=False, server_default="SISTEMA")
    problema: Mapped[str] = mapped_column("Problema", String(500), nullable=False)
    detalle: Mapped[str | None] = mapped_column("Detalle", Text)
    responsable_dia_id: Mapped[int | None] = mapped_column("ResponsableDiaId", Integer, ForeignKey("cat_usuarios.UsuarioId"))
    usuario_atendio_id: Mapped[int | None] = mapped_column("UsuarioAtendioId", Integer, ForeignKey("cat_usuarios.UsuarioId"))
    accion_tomada: Mapped[str | None] = mapped_column("AccionTomada", Text)
    resultado: Mapped[str | None] = mapped_column("Resultado", String(15))
    fecha_resolucion: Mapped[datetime | None] = mapped_column("FechaResolucion", DateTime(0))
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class AccionIncidencia(Base):
    __tablename__ = "acciones_incidencia"

    accion_incidencia_id: Mapped[int] = mapped_column("AccionIncidenciaId", Integer, primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column("IncidenciaId", Integer, ForeignKey("incidencias.IncidenciaId"), nullable=False)
    usuario_id: Mapped[int] = mapped_column("UsuarioId", Integer, ForeignKey("cat_usuarios.UsuarioId"), nullable=False)
    fecha_accion: Mapped[datetime] = mapped_column("FechaAccion", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
    descripcion: Mapped[str] = mapped_column("Descripcion", Text, nullable=False)
    resultado: Mapped[str | None] = mapped_column("Resultado", String(15))


class Alerta(Base):
    __tablename__ = "alertas"

    alerta_id: Mapped[int] = mapped_column("AlertaId", Integer, primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int | None] = mapped_column("IncidenciaId", Integer, ForeignKey("incidencias.IncidenciaId"))
    ejecucion_id: Mapped[int | None] = mapped_column("EjecucionId", BigInteger, ForeignKey("respaldos_ejecuciones.EjecucionId"))
    tipo_evento: Mapped[str] = mapped_column("TipoEvento", String(30), nullable=False)
    asunto: Mapped[str] = mapped_column("Asunto", String(200), nullable=False)
    cuerpo: Mapped[str | None] = mapped_column("Cuerpo", Text)
    destinatarios: Mapped[str | None] = mapped_column("Destinatarios", String(500))
    estado: Mapped[str] = mapped_column("Estado", String(15), nullable=False, server_default="ENVIADA")
    fecha_envio: Mapped[datetime | None] = mapped_column("FechaEnvio", DateTime(0))
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class ResponsableDia(Base):
    __tablename__ = "responsables_dia"

    responsable_dia_id: Mapped[int] = mapped_column("ResponsableDiaId", Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column("Fecha", Date, nullable=False, unique=True)
    usuario_id: Mapped[int] = mapped_column("UsuarioId", Integer, ForeignKey("cat_usuarios.UsuarioId"), nullable=False)
    origen_asignacion: Mapped[str] = mapped_column("OrigenAsignacion", String(10), nullable=False, server_default="AUTO")
    usuario_reasigno_id: Mapped[int | None] = mapped_column("UsuarioReasignoId", Integer, ForeignKey("cat_usuarios.UsuarioId"))
    fecha_asignacion: Mapped[datetime] = mapped_column("FechaAsignacion", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class Rotacion(Base):
    __tablename__ = "rotacion"

    rotacion_id: Mapped[int] = mapped_column("RotacionId", Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column("UsuarioId", Integer, ForeignKey("cat_usuarios.UsuarioId"), nullable=False)
    orden: Mapped[int] = mapped_column("Orden", Integer, nullable=False, unique=True)
    suspendido: Mapped[bool] = mapped_column("Suspendido", Boolean, nullable=False, server_default="0")
    fecha_alta: Mapped[datetime] = mapped_column("FechaAlta", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
