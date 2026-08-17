"""Simula 24 pasos de DepurarLogs y valida ingesta e idempotencia."""
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "agente"))
sys.path.insert(0, str(RAIZ / "backend"))

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.api.v1 import jobs  # noqa: E402
from app.models import JobsPasoEjecucion  # noqa: E402
from app.schemas.operacion import JobPasoEjecucionCreate  # noqa: E402
from checkers.jobs_checker import JobsChecker  # noqa: E402


class JobsSimuladosTest(unittest.TestCase):
    def test_pendiente_se_clasifica_segun_horario(self) -> None:
        body = JobPasoEjecucionCreate(
            paso_monitoreado_id=1,
            fecha_ejecucion=date(2026, 8, 16),
            hora_esperada=time(21, 0),
            estado="PENDIENTE",
            mensaje="No ejecutado",
        )
        antes = datetime(2026, 8, 16, 21, 20, tzinfo=timezone.utc)
        despues = datetime(2026, 8, 16, 21, 31, tzinfo=timezone.utc)
        aplica = SimpleNamespace(dia_aplica=True, hora_esperada=time(21, 0), tolerancia_minutos=30)
        no_aplica = SimpleNamespace(dia_aplica=False, hora_esperada=time(21, 0), tolerancia_minutos=30)

        self.assertEqual(jobs.resolver_estado_pendiente(body, aplica, antes)[0], "PENDIENTE")
        self.assertEqual(jobs.resolver_estado_pendiente(body, aplica, despues)[0], "ERROR")
        self.assertEqual(jobs.resolver_estado_pendiente(body, no_aplica, despues)[0], "NO_APLICA")

    def test_depurar_logs_24_pasos_sin_duplicados(self) -> None:
        engine = create_engine("sqlite://")
        self._crear_esquema(engine)
        sesiones = sessionmaker(bind=engine, expire_on_commit=False)
        payloads = self._payloads_csv()

        self.assertEqual(len(payloads), 24)
        self.assertEqual([p["estado"] for p in payloads[:3]], ["OK", "ERROR", "PENDIENTE"])

        agente = SimpleNamespace(servidor_id=10)
        with sesiones() as db, patch.object(
            jobs,
            "crear_o_reutilizar_incidencia_servidor",
            return_value=SimpleNamespace(incidencia_id=900),
        ) as crear_incidencia:
            primera = self._reportar_todos(db, agente, payloads)
            segunda = self._reportar_todos(db, agente, payloads)

            self.assertEqual(db.scalar(select(func.count()).select_from(JobsPasoEjecucion)), 24)
            self.assertEqual({r.ejecucion_id for r in primera}, {r.ejecucion_id for r in segunda})
            crear_incidencia.assert_called_once()

            por_estado = {r.estado: r for r in primera[:3]}
            self.assertIsNone(por_estado["OK"].incidencia_id)
            self.assertEqual(por_estado["ERROR"].incidencia_id, 900)
            self.assertIsNone(por_estado["PENDIENTE"].incidencia_id)

    def test_falla_temprana_no_es_ocultada_por_exito_tardio(self) -> None:
        engine = create_engine("sqlite://")
        self._crear_esquema(engine)
        sesiones = sessionmaker(bind=engine, expire_on_commit=False)
        agente = SimpleNamespace(servidor_id=10)
        temprano = JobPasoEjecucionCreate(
            paso_monitoreado_id=1, fecha_ejecucion=date(2026, 8, 16),
            hora_esperada=time(10, 0), estado="ERROR", mensaje="Falló 10:00",
        )
        tardio = JobPasoEjecucionCreate(
            paso_monitoreado_id=1, fecha_ejecucion=date(2026, 8, 16),
            hora_esperada=time(12, 0), estado="OK", mensaje="Correcto 12:00",
        )
        with sesiones() as db, patch.object(
            jobs, "crear_o_reutilizar_incidencia_servidor",
            return_value=SimpleNamespace(incidencia_id=901),
        ):
            jobs.reportar_ejecucion_job(temprano, agente, db)
            jobs.reportar_ejecucion_job(tardio, agente, db)
            filas = db.scalars(select(JobsPasoEjecucion).order_by(JobsPasoEjecucion.hora_esperada)).all()
            self.assertEqual([(f.hora_esperada, f.estado) for f in filas], [(time(10, 0), "ERROR"), (time(12, 0), "OK")])
            self.assertEqual(filas[0].incidencia_id, 901)
            self.assertIsNone(filas[1].incidencia_id)

    @staticmethod
    def _reportar_todos(db, agente, payloads: list[dict]) -> list:
        return [
            jobs.reportar_ejecucion_job(JobPasoEjecucionCreate(**payload), agente, db)
            for payload in payloads
        ]

    @staticmethod
    def _payloads_csv() -> list[dict]:
        resultados = ["Succeeded", "Failed", "NotRun"] + ["Succeeded"] * 21
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "resultado.csv"
            filas = [
                f'"{step}","DepurarLogs","{step}","21:00:00","{resultado}",'
                f'"{"" if resultado == "NotRun" else f"2026-08-16T23:{step:02d}:00"}",'
                f'"Mensaje simulado paso {step}"'
                for step, resultado in enumerate(resultados, start=1)
            ]
            ruta.write_text("\n".join(filas), encoding="utf-8")
            return JobsChecker._leer_csv(ruta, date(2026, 8, 16))

    @staticmethod
    def _crear_esquema(engine) -> None:
        with engine.begin() as conexion:
            conexion.execute(text("""
                CREATE TABLE cat_jobs_monitoreados (
                    JobMonitoreadoId INTEGER PRIMARY KEY,
                    ServidorId INTEGER, NombreJob TEXT, Activo BOOLEAN
                )
            """))
            conexion.execute(text("""
                CREATE TABLE cat_pasos_monitoreados (
                    PasoMonitoreadoId INTEGER PRIMARY KEY,
                    JobMonitoreadoId INTEGER, StepId INTEGER,
                    NombrePaso TEXT, Activo BOOLEAN
                )
            """))
            conexion.execute(text("""
                CREATE TABLE jobs_pasos_ejecuciones (
                    EjecucionId INTEGER PRIMARY KEY AUTOINCREMENT,
                    PasoMonitoreadoId INTEGER, FechaEjecucion DATE,
                    HoraEsperada TIME,
                    Estado TEXT, FechaHoraReal DATETIME, Mensaje TEXT,
                    IncidenciaId INTEGER,
                    UNIQUE(PasoMonitoreadoId, FechaEjecucion, HoraEsperada)
                )
            """))
            conexion.execute(text("""
                CREATE TABLE pasos_horarios_esperados (
                    PasoHorarioEsperadoId INTEGER PRIMARY KEY AUTOINCREMENT,
                    PasoMonitoreadoId INTEGER, DiaSemana INTEGER,
                    DiaAplica BOOLEAN, HoraEsperada TIME,
                    ToleranciaMinutos INTEGER,
                    UNIQUE(PasoMonitoreadoId, DiaSemana, HoraEsperada)
                )
            """))
            conexion.execute(text("INSERT INTO cat_jobs_monitoreados VALUES (1, 10, 'DepurarLogs', 1)"))
            for step in range(1, 25):
                conexion.execute(
                    text("""
                        INSERT INTO cat_pasos_monitoreados
                        VALUES (:step, 1, :step, :nombre, 1)
                    """),
                    {"step": step, "nombre": f"DepurarLogs paso {step}"},
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
