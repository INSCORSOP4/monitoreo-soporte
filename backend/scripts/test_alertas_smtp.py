"""Prueba aislada de alertas con SQLite y un SMTP local de captura."""
from __future__ import annotations

import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Alerta  # noqa: E402
from app.services import alertas_service  # noqa: E402


class SMTPCapturaHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.wfile.write(b"220 localhost SMTP de prueba\r\n")
        while linea := self.rfile.readline():
            comando = linea.decode("utf-8", errors="replace").strip()
            if comando.upper().startswith("DATA"):
                self.wfile.write(b"354 Termina con punto\r\n")
                contenido = []
                while (linea := self.rfile.readline()) != b".\r\n":
                    contenido.append(linea)
                self.server.mensajes.append(b"".join(contenido).decode("utf-8"))
                self.wfile.write(b"250 Mensaje capturado\r\n")
            elif comando.upper().startswith("QUIT"):
                self.wfile.write(b"221 Adios\r\n")
                return
            else:
                self.wfile.write(b"250 OK\r\n")


class SMTPCapturaServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), SMTPCapturaHandler)
        self.mensajes: list[str] = []


class AlertasSMTPTest(unittest.TestCase):
    def test_flujo_completo(self) -> None:
        with tempfile.TemporaryDirectory() as temporal:
            engine = create_engine(f"sqlite:///{Path(temporal) / 'alertas.db'}")
            self._crear_esquema(engine)
            sesiones = sessionmaker(bind=engine, expire_on_commit=False)
            servidor = SMTPCapturaServer()
            hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
            hilo.start()

            valores_originales = self._configurar_smtp(servidor.server_address[1])
            sesiones_original = alertas_service.SessionLocal
            alertas_service.SessionLocal = sesiones
            try:
                self._probar_idempotencia(sesiones, servidor)
                servidor.shutdown()
                servidor.server_close()
                hilo.join(timeout=2)
                self._probar_smtp_caido(sesiones)
            finally:
                alertas_service.SessionLocal = sesiones_original
                self._restaurar_smtp(valores_originales)
                engine.dispose()

    def _probar_idempotencia(self, sesiones: sessionmaker, servidor: SMTPCapturaServer) -> None:
        alerta_error = self._crear_alerta(sesiones, "ERROR", incidencia_id=101)
        self.assertIsNotNone(alerta_error)
        alertas_service.enviar_alerta(alerta_error)
        self.assertEqual(self._estado(sesiones, alerta_error), "ENVIADA")
        self.assertIsNone(self._crear_alerta(sesiones, "ERROR", incidencia_id=101))
        self.assertEqual(self._cantidad(sesiones, "ERROR", "IncidenciaId", 101), 1)

        alerta_advertencia = self._crear_alerta(sesiones, "ADVERTENCIA", ejecucion_id=202)
        self.assertIsNotNone(alerta_advertencia)
        alertas_service.enviar_alerta(alerta_advertencia)
        self.assertEqual(self._estado(sesiones, alerta_advertencia), "ENVIADA")
        self.assertIsNone(self._crear_alerta(sesiones, "ADVERTENCIA", ejecucion_id=202))
        self.assertEqual(self._cantidad(sesiones, "ADVERTENCIA", "EjecucionId", 202), 1)
        self.assertEqual(len(servidor.mensajes), 2)
        self.assertIn("Subject: [QA] ERROR", servidor.mensajes[0])
        self.assertIn("Subject: [QA] ADVERTENCIA", servidor.mensajes[1])

    def _probar_smtp_caido(self, sesiones: sessionmaker) -> None:
        alerta_id = self._crear_alerta(sesiones, "ADVERTENCIA", lectura_id=303)
        app = FastAPI()

        @app.post("/ingesta")
        def ingesta(background_tasks: BackgroundTasks) -> dict[str, bool]:
            background_tasks.add_task(alertas_service.enviar_alerta, alerta_id)
            return {"ingesta": True}

        respuesta = TestClient(app).post("/ingesta")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"ingesta": True})
        with sesiones() as db:
            alerta = db.get(Alerta, alerta_id)
            self.assertEqual(alerta.estado, "FALLIDA")
            self.assertTrue(alerta.error_detalle)

    @staticmethod
    def _crear_alerta(
        sesiones: sessionmaker,
        tipo_evento: str,
        incidencia_id: int | None = None,
        ejecucion_id: int | None = None,
        lectura_id: int | None = None,
    ) -> int | None:
        with sesiones() as db:
            alerta = alertas_service.crear_alerta_si_no_existe(
                db,
                tipo_evento,
                incidencia_id=incidencia_id,
                ejecucion_id=ejecucion_id,
                lectura_id=lectura_id,
            )
            if alerta is not None:
                alerta.asunto = f"[QA] {tipo_evento}"
                alerta.cuerpo = f"Mensaje aislado de prueba: {tipo_evento}"
            db.commit()
            return alerta.alerta_id if alerta is not None else None

    @staticmethod
    def _estado(sesiones: sessionmaker, alerta_id: int) -> str:
        with sesiones() as db:
            return db.get(Alerta, alerta_id).estado

    @staticmethod
    def _cantidad(sesiones: sessionmaker, tipo: str, columna: str, valor: int) -> int:
        with sesiones() as db:
            return db.scalar(
                select(func.count()).select_from(Alerta).where(
                    Alerta.tipo_evento == tipo,
                    getattr(Alerta, {
                        "IncidenciaId": "incidencia_id",
                        "EjecucionId": "ejecucion_id",
                    }[columna]) == valor,
                )
            )

    @staticmethod
    def _configurar_smtp(puerto: int) -> tuple[object, ...]:
        campos = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_tls", "smtp_timeout")
        originales = tuple(getattr(alertas_service.settings, campo) for campo in campos)
        valores = ("127.0.0.1", puerto, "", "", "qa-alertas@example.test", False, 1)
        for campo, valor in zip(campos, valores, strict=True):
            setattr(alertas_service.settings, campo, valor)
        return originales

    @staticmethod
    def _restaurar_smtp(originales: tuple[object, ...]) -> None:
        campos = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_tls", "smtp_timeout")
        for campo, valor in zip(campos, originales, strict=True):
            setattr(alertas_service.settings, campo, valor)

    @staticmethod
    def _crear_esquema(engine) -> None:
        with engine.begin() as conexion:
            conexion.execute(text("""
                CREATE TABLE cat_roles (
                    RolId INTEGER PRIMARY KEY, Codigo VARCHAR(20), Activo BOOLEAN
                );
            """))
            conexion.execute(text("""
                CREATE TABLE cat_usuarios (
                    UsuarioId INTEGER PRIMARY KEY, Correo VARCHAR(120), RolId INTEGER, Activo BOOLEAN
                );
            """))
            conexion.execute(text("""
                CREATE TABLE alertas (
                    AlertaId INTEGER PRIMARY KEY AUTOINCREMENT,
                    IncidenciaId INTEGER, EjecucionId INTEGER, LecturaDiscoId INTEGER,
                    TipoEvento VARCHAR(30) NOT NULL, Asunto VARCHAR(200) NOT NULL,
                    Cuerpo TEXT, Destinatarios VARCHAR(500), Estado VARCHAR(15) NOT NULL,
                    ErrorDetalle TEXT, FechaEnvio DATETIME, FechaRegistro DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conexion.execute(text("""
                CREATE UNIQUE INDEX uq_alertas_error
                ON alertas (IncidenciaId)
                WHERE TipoEvento = 'ERROR' AND IncidenciaId IS NOT NULL;
            """))
            conexion.execute(text("""
                CREATE UNIQUE INDEX uq_alertas_advertencia_ejecucion
                ON alertas (TipoEvento, EjecucionId) WHERE EjecucionId IS NOT NULL;
            """))
            conexion.execute(text("""
                CREATE UNIQUE INDEX uq_alertas_advertencia_lectura
                ON alertas (TipoEvento, LecturaDiscoId) WHERE LecturaDiscoId IS NOT NULL;
            """))
            conexion.execute(text("INSERT INTO cat_roles VALUES (1, 'SOPORTE', 1)"))
            conexion.execute(text("""
                INSERT INTO cat_usuarios VALUES (1, 'qa-soporte@example.test', 1, 1)
            """))


if __name__ == "__main__":
    unittest.main(verbosity=2)
