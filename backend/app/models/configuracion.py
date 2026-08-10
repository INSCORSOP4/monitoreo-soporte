"""Modelos ORM — Configuración de respaldos (secciones 2.1 a 2.3 del DDL)."""
from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RutaOrigenDestino(Base):
    __tablename__ = "rutas_origen_destino"

    ruta_origen_destino_id: Mapped[int] = mapped_column("RutaOrigenDestinoId", Integer, primary_key=True, autoincrement=True)
    base_datos_id: Mapped[int] = mapped_column("BaseDatosId", Integer, ForeignKey("cat_bases_datos.BaseDatosId"), nullable=False, unique=True)
    ruta_origen: Mapped[str] = mapped_column("RutaOrigen", String(500), nullable=False)
    ruta_destino: Mapped[str] = mapped_column("RutaDestino", String(500), nullable=False)
    servidor_destino_id: Mapped[int | None] = mapped_column("ServidorDestinoId", Integer, ForeignKey("cat_servidores.ServidorId"))
    eliminar_origen_tras_transferencia: Mapped[bool] = mapped_column("EliminarOrigenTrasTransferencia", Boolean, nullable=False, server_default="1")
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class HorarioEsperado(Base):
    __tablename__ = "horarios_esperados"

    horario_esperado_id: Mapped[int] = mapped_column("HorarioEsperadoId", Integer, primary_key=True, autoincrement=True)
    base_datos_id: Mapped[int] = mapped_column("BaseDatosId", Integer, ForeignKey("cat_bases_datos.BaseDatosId"), nullable=False)
    dia_semana: Mapped[int] = mapped_column("DiaSemana", Integer, nullable=False)  # 1=Lun ... 7=Dom
    dia_aplica: Mapped[bool] = mapped_column("DiaAplica", Boolean, nullable=False, server_default="1")
    tipo_backup_esperado: Mapped[str] = mapped_column("TipoBackupEsperado", String(15), nullable=False)
    hora_esperada: Mapped[time] = mapped_column("HoraEsperada", Time(0), nullable=False)
    tolerancia_minutos: Mapped[int] = mapped_column("ToleranciaMinutos", Integer, nullable=False, server_default="180")
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))


class ReglaRetencion(Base):
    __tablename__ = "reglas_retencion"

    regla_retencion_id: Mapped[int] = mapped_column("ReglaRetencionId", Integer, primary_key=True, autoincrement=True)
    grupo_respaldo_id: Mapped[int] = mapped_column("GrupoRespaldoId", Integer, ForeignKey("cat_grupos_respaldo.GrupoRespaldoId"), nullable=False, unique=True)
    meses_retencion: Mapped[int] = mapped_column("MesesRetencion", Integer, nullable=False, server_default="3")
    conservar_full_por_mes: Mapped[int] = mapped_column("ConservarFullPorMes", Integer, nullable=False, server_default="1")
    conservar_diferencial_por_mes: Mapped[int] = mapped_column("ConservarDiferencialPorMes", Integer, nullable=False, server_default="1")
    depuracion_activa: Mapped[bool] = mapped_column("DepuracionActiva", Boolean, nullable=False, server_default="0")
    activo: Mapped[bool] = mapped_column("Activo", Boolean, nullable=False, server_default="1")
    fecha_registro: Mapped[datetime] = mapped_column("FechaRegistro", DateTime(0), nullable=False, server_default=text("SYSDATETIME()"))
