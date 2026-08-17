"""Alertas por correo (§28) — envío SMTP + bitácora con anti-spam por ENTIDAD.

ADVERTENCIA no crea incidencia (por diseño desde el inicio), así que la alerta
NO puede deduplicarse solo por IncidenciaId. Cada alerta se deduplica por la
entidad que la originó (barrera BD: índices únicos filtrados en dbo.alertas):

  ERROR de respaldo      -> IncidenciaId  (incidencia SISTEMA creada en §26)
  ADVERTENCIA de respaldo -> EjecucionId  (idempotente por base+fecha)
  ERROR de disco         -> IncidenciaId  (incidencia DISCO_SERVIDOR)
  ADVERTENCIA de disco   -> LecturaDiscoId (idempotente por servidor+unidad+fecha)

Ciclo de vida de la fila en alertas:
  - Se crea con Estado='PENDIENTE' en la transacción de ingesta.
  - FastAPI intenta el envío SMTP en segundo plano, después de responder.
  - Éxito  -> ENVIADA + FechaEnvio.
  - Falla  -> FALLIDA + ErrorDetalle; un proceso separado puede reintentarla.

Destinatarios: se consultan al intentar cada envío entre los usuarios Activo=1
del rol configurable ALERTA_ROL_DESTINATARIOS; la alerta no guarda una lista
fija. smtplib de la librería estándar, sin pip.
"""
import smtplib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models import Alerta, CatAgente, CatBaseDatos, CatRol, CatServidor, CatUsuario, DiscosLectura, RespaldoEjecucion

logger = get_logger(__name__)


class SMTPNoConfigurado(Exception):
    """SMTP_HOST/FROM vacíos en .env."""


def destinatarios_soporte(db: Session) -> list[str]:
    """Correos de los usuarios Activo=1 del rol de alertas (default SOPORTE)."""
    filas = db.execute(
        select(CatUsuario.correo)
        .join(CatRol, CatRol.rol_id == CatUsuario.rol_id)
        .where(
            CatRol.codigo == settings.alerta_rol_destinatarios,
            CatUsuario.activo == True,  # noqa: E712 (SQL Server: = 1)
        )
    ).all()
    return [f.correo for f in filas]


def _buscar_existente(
    db: Session,
    *,
    tipo_evento: str,
    incidencia_id: int | None = None,
    ejecucion_id: int | None = None,
    lectura_disco_id: int | None = None,
) -> Alerta | None:
    """Fila previa de la misma entidad (la clave de dedupe exacta del §28)."""
    stmt = select(Alerta).where(Alerta.tipo_evento == tipo_evento)
    if incidencia_id is not None:
        stmt = stmt.where(Alerta.incidencia_id == incidencia_id)
    elif ejecucion_id is not None:
        stmt = stmt.where(Alerta.ejecucion_id == ejecucion_id)
    elif lectura_disco_id is not None:
        stmt = stmt.where(Alerta.lectura_disco_id == lectura_disco_id)
    else:
        return None
    return db.scalar(stmt)


def crear_alerta_si_no_existe(
    db: Session,
    tipo_evento: str,
    incidencia_id: int | None = None,
    ejecucion_id: int | None = None,
    lectura_id: int | None = None,
) -> Alerta | None:
    """Inserta una alerta PENDIENTE; el índice único resuelve la idempotencia."""
    alerta = Alerta(
        tipo_evento=tipo_evento,
        asunto="Pendiente de envío",
        estado="PENDIENTE",
        incidencia_id=incidencia_id,
        ejecucion_id=ejecucion_id,
        lectura_disco_id=lectura_id,
    )
    try:
        with db.begin_nested():
            db.add(alerta)
            db.flush()
    except IntegrityError:
        if _buscar_existente(
            db,
            tipo_evento=tipo_evento,
            incidencia_id=incidencia_id,
            ejecucion_id=ejecucion_id,
            lectura_disco_id=lectura_id,
        ) is None:
            raise
        return None
    return alerta


def _enviar_smtp(asunto: str, cuerpo: str, destinatarios: list[str]) -> None:
    """Envía el correo con smtplib (stdlib). Lanza SMTPNoConfigurado o la excepción SMTP."""
    if not settings.smtp_host or not settings.smtp_from:
        raise SMTPNoConfigurado("SMTP_HOST/FROM vacíos en .env")

    # Header injection: el asunto puede contener nombres de base — nunca \r\n.
    asunto_limpio = " ".join(asunto.splitlines())
    mensaje = (
        f"From: {settings.smtp_from}\r\n"
        f"To: {', '.join(destinatarios)}\r\n"
        f"Subject: {asunto_limpio}\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{cuerpo}"
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as smtp:
        smtp.ehlo()
        if settings.smtp_tls:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.smtp_from, destinatarios, mensaje.encode("utf-8"))


def enviar_alerta(alerta_id: int) -> None:
    """Envía una alerta en segundo plano usando una sesión independiente."""
    with SessionLocal() as db:
        alerta = db.get(Alerta, alerta_id)
        if alerta is None or alerta.estado in ("ENVIADA", "SUPRIMIDA"):
            return

        try:
            destinatarios = destinatarios_soporte(db)
            if not destinatarios:
                raise RuntimeError(f"No hay usuarios activos del rol {settings.alerta_rol_destinatarios}")
            _enviar_smtp(alerta.asunto, alerta.cuerpo or "", destinatarios)
        except Exception as exc:  # noqa: BLE001 — el fallo queda disponible para reintento
            alerta.estado = "FALLIDA"
            alerta.error_detalle = str(exc)
            db.commit()
            logger.error("Alerta #%s FALLIDA (%s): %s", alerta.alerta_id, alerta.asunto, exc)
            return

        alerta.estado = "ENVIADA"
        alerta.error_detalle = None
        alerta.fecha_envio = datetime.now(timezone.utc)
        db.commit()
        logger.info("Alerta #%s ENVIADA a %s: %s", alerta.alerta_id, "; ".join(destinatarios), alerta.asunto)


def preparar_alerta_respaldo(
    alerta: Alerta, *, ejecucion: RespaldoEjecucion, base: CatBaseDatos, agente: CatAgente
) -> None:
    """Completa el mensaje de una alerta de respaldo antes del commit."""
    tipo_evento = ejecucion.estado
    asunto = f"[MONITOREO] {tipo_evento} — Respaldo {base.nombre_base} ({ejecucion.fecha_ejecucion})"
    cuerpo = (
        f"Estado: {ejecucion.estado}\n"
        f"Base de datos: {base.nombre_base}\n"
        f"Fecha: {ejecucion.fecha_ejecucion}\n"
        f"Reportado por: {agente.nombre}\n"
        f"Archivo: {ejecucion.archivo_encontrado or 'n/d'}\n"
        f"Tamaño: {ejecucion.tamano_bytes or 'n/d'} bytes\n"
        f"Fuera de horario: {'sí' if ejecucion.fuera_de_horario else 'no'}\n"
        f"Detalle: {ejecucion.detalle or 'n/d'}\n"
        f"Ejecución #: {ejecucion.ejecucion_id}"
    )

    alerta.asunto = asunto[:200]
    alerta.cuerpo = cuerpo
    alerta.destinatarios = None


def preparar_alerta_disco(
    alerta: Alerta, *, lectura: DiscosLectura, servidor: CatServidor, agente: CatAgente
) -> None:
    """Completa el mensaje de una alerta de disco antes del commit."""
    tipo_evento = lectura.estado
    asunto = f"[MONITOREO] {tipo_evento} — Disco {servidor.nombre} ({lectura.unidad_letra})"
    cuerpo = (
        f"Estado: {lectura.estado}\n"
        f"Servidor: {servidor.nombre}\n"
        f"Unidad: {lectura.unidad_letra}\n"
        f"Fecha: {lectura.fecha_lectura}\n"
        f"Reportado por: {agente.nombre}\n"
        f"Espacio libre: {lectura.espacio_libre_gb:,.2f} GB de {lectura.espacio_total_gb:,.2f} GB "
        f"({lectura.porcentaje_libre:.2f}%)\n"
        f"Detalle: {lectura.detalle or 'n/d'}\n"
        f"Lectura #: {lectura.lectura_id}"
    )

    alerta.asunto = asunto[:200]
    alerta.cuerpo = cuerpo
    alerta.destinatarios = None
