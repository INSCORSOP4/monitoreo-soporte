"""Valida pasos monitoreados de SQL Server Agent mediante sqlcmd y CSV."""
import csv
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


class JobsCheckerError(RuntimeError):
    """No fue posible consultar o interpretar el historial de SQL Agent."""


class JobsChecker:
    def __init__(self, usuario: str, password: str, servidor: str = "localhost"):
        self._usuario = usuario
        self._password = password
        self._servidor = servidor

    def check(self, pasos: list[dict], fecha: date) -> list[dict]:
        if not pasos:
            return []
        if not self._usuario or not self._password:
            raise JobsCheckerError("SQL_JOBS_USER/SQL_JOBS_PASSWORD no están configurados")

        sqlcmd = shutil.which("sqlcmd")
        if sqlcmd is None:
            raise JobsCheckerError("sqlcmd no está instalado o no está en PATH")

        with tempfile.TemporaryDirectory(prefix="monitoreo_jobs_") as temporal:
            resultado = Path(temporal) / "resultado.csv"
            self._ejecutar_sqlcmd(sqlcmd, self._consulta(pasos, fecha), resultado)
            return self._leer_csv(resultado, fecha)

    def _ejecutar_sqlcmd(self, sqlcmd: str, consulta: str, resultado: Path) -> None:
        comando = [
            sqlcmd,
            "-S", self._servidor,
            "-U", self._usuario,
            "-P", self._password,
            "-d", "msdb",
            "-Q", consulta,
            "-s", ",",
            "-W",
            "-h", "-1",
            "-f", "65001",
            "-b",
            "-o", str(resultado),
        ]
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if proceso.returncode != 0:
            detalle = (proceso.stderr or proceso.stdout or "sqlcmd terminó con error").strip()
            raise JobsCheckerError(detalle)

    @staticmethod
    def _leer_csv(ruta: Path, fecha: date) -> list[dict]:
        payloads = []
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            for numero, fila in enumerate(csv.reader(archivo), start=1):
                if not fila or all(not campo.strip() for campo in fila):
                    continue
                if len(fila) != 7:
                    raise JobsCheckerError(f"CSV inválido en fila {numero}: se esperaban 7 columnas")
                paso_id, nombre_job, step_id, hora_esperada, resultado, fecha_hora, mensaje = fila
                payloads.append(
                    {
                        "paso_monitoreado_id": int(paso_id),
                        "fecha_ejecucion": fecha.isoformat(),
                        "hora_esperada": hora_esperada,
                        "estado": {
                            "Succeeded": "OK",
                            "NotRun": "PENDIENTE",
                            "NotApplicable": "NO_APLICA",
                        }.get(resultado, "ERROR"),
                        "fecha_hora_real": fecha_hora or None,
                        "mensaje": mensaje[:500] or (
                            f"Sin ejecución Succeeded hoy: {nombre_job}, step {step_id}"
                        ),
                    }
                )
        return payloads

    @classmethod
    def _consulta(cls, pasos: list[dict], fecha: date) -> str:
        ventanas = [
            (p, h)
            for p in pasos
            for h in p.get("horarios", [])
            if int(h["dia_semana"]) == fecha.isoweekday()
        ]
        if not ventanas:
            raise JobsCheckerError("No hay ventanas configuradas para la fecha operativa")
        valores = ",\n".join(
            f"({int(p['paso_monitoreado_id'])}, N'{cls._sql_texto(p['nombre_job'])}', {int(p['step_id'])}, "
            f"CAST('{h['hora_esperada']}' AS time(0)), {int(h['tolerancia_minutos'])}, {1 if h['dia_aplica'] else 0})"
            for p, h in ventanas
        )
        fecha_sql = fecha.strftime("%Y%m%d")
        return f"""
SET NOCOUNT ON;
WITH Monitoreados (PasoMonitoreadoId, NombreJob, StepId, HoraEsperada, ToleranciaMinutos, DiaAplica) AS (
    SELECT * FROM (VALUES
        {valores}
    ) AS v (PasoMonitoreadoId, NombreJob, StepId, HoraEsperada, ToleranciaMinutos, DiaAplica)
), Historial AS (
    SELECT
        m.PasoMonitoreadoId,
        m.HoraEsperada AS HoraEsperadaVentana,
        h.run_status,
        DATETIMEFROMPARTS(
            h.run_date / 10000,
            (h.run_date % 10000) / 100,
            h.run_date % 100,
            h.run_time / 10000,
            (h.run_time % 10000) / 100,
            h.run_time % 100,
            0
        ) AS FechaHoraReal,
        h.message,
        ROW_NUMBER() OVER (
            PARTITION BY m.PasoMonitoreadoId, m.HoraEsperada
            ORDER BY ABS(DATEDIFF(SECOND, DATEADD(SECOND, DATEDIFF(SECOND, 0, m.HoraEsperada), CAST('{fecha.isoformat()}' AS datetime2)),
                                           DATETIMEFROMPARTS(h.run_date / 10000, (h.run_date % 10000) / 100, h.run_date % 100, h.run_time / 10000, (h.run_time % 10000) / 100, h.run_time % 100, 0))), h.instance_id DESC
        ) AS rn
    FROM Monitoreados m
    JOIN msdb.dbo.sysjobs j ON j.name = m.NombreJob
    JOIN msdb.dbo.sysjobhistory h ON h.job_id = j.job_id AND h.step_id = m.StepId
    WHERE h.run_date = {fecha_sql}
      AND m.DiaAplica = 1
      AND DATETIMEFROMPARTS(h.run_date / 10000, (h.run_date % 10000) / 100, h.run_date % 100, h.run_time / 10000, (h.run_time % 10000) / 100, h.run_time % 100, 0)
          BETWEEN DATEADD(SECOND, DATEDIFF(SECOND, 0, m.HoraEsperada), CAST('{fecha.isoformat()}' AS datetime2))
              AND DATEADD(MINUTE, m.ToleranciaMinutos, DATEADD(SECOND, DATEDIFF(SECOND, 0, m.HoraEsperada), CAST('{fecha.isoformat()}' AS datetime2)))
)
SELECT
    CHAR(34) + CONVERT(varchar(20), m.PasoMonitoreadoId) + CHAR(34),
    CHAR(34) + REPLACE(m.NombreJob, CHAR(34), CHAR(34) + CHAR(34)) + CHAR(34),
    CHAR(34) + CONVERT(varchar(20), m.StepId) + CHAR(34),
    CHAR(34) + CONVERT(varchar(8), m.HoraEsperada, 108) + CHAR(34),
    CHAR(34) + CASE WHEN m.DiaAplica = 0 THEN 'NotApplicable'
               WHEN h.run_status = 1 THEN 'Succeeded'
               WHEN h.run_status IS NULL THEN 'NotRun'
               ELSE 'Failed' END + CHAR(34),
    CHAR(34) + COALESCE(CONVERT(varchar(19), h.FechaHoraReal, 126), '') + CHAR(34),
    CHAR(34) + REPLACE(REPLACE(REPLACE(
        COALESCE(h.message, 'No se encontró ejecución del paso en la fecha operativa'),
        CHAR(34), CHAR(34) + CHAR(34)), CHAR(13), ' '), CHAR(10), ' ') + CHAR(34)
FROM Monitoreados m
LEFT JOIN Historial h ON h.PasoMonitoreadoId = m.PasoMonitoreadoId
    AND h.HoraEsperadaVentana = m.HoraEsperada AND h.rn = 1
ORDER BY m.PasoMonitoreadoId, m.HoraEsperada;
""".strip()

    @staticmethod
    def _sql_texto(valor: str) -> str:
        return str(valor).replace("'", "''")
