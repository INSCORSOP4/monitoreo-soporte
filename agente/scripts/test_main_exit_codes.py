"""Verifica la convención 0=OK, 1=problema real, 2=falla del checker."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as agent_main  # noqa: E402
from checkers.jobs_checker import JobsCheckerError  # noqa: E402


class ApiFalsa:
    def get_configuracion(self) -> dict:
        return {
            "agente_nombre": "QA",
            "servidor_id": None,
            "bases": [],
            "jobs_pasos": [{
                "paso_monitoreado_id": 1,
                "nombre_job": "Job QA",
                "nombre_paso": "Paso QA",
                "step_id": 1,
            }],
        }

    @staticmethod
    def reportar_ejecucion_job(payload: dict) -> dict:
        return {"ejecucion_id": 1, "estado": payload["estado"], "incidencia_id": 2 if payload["estado"] == "ERROR" else None}


class ExitCodesTest(unittest.TestCase):
    def test_fallos_tecnicos_de_msdb_devuelven_2(self) -> None:
        for detalle in ("Credenciales vacías", "sqlcmd terminó con error", "CSV inválido"):
            with self.subTest(detalle=detalle):
                self.assertEqual(self._ejecutar(error=JobsCheckerError(detalle)), 2)

    def test_job_fallido_devuelve_1(self) -> None:
        self.assertEqual(self._ejecutar(estado="ERROR"), 1)

    def test_jobs_correctos_devuelven_0(self) -> None:
        self.assertEqual(self._ejecutar(estado="OK"), 0)

    @staticmethod
    def _ejecutar(estado: str = "OK", error: Exception | None = None) -> int:
        checker = MagicMock()
        if error is not None:
            checker.check.side_effect = error
        else:
            checker.check.return_value = [{
                "paso_monitoreado_id": 1,
                "fecha_ejecucion": "2026-08-16",
                "hora_esperada": "10:00:00",
                "estado": estado,
                "fecha_hora_real": None,
                "mensaje": "QA",
            }]

        with patch.object(agent_main, "AGENT_API_KEY", "qa-key"), \
             patch.object(agent_main, "ApiClient", return_value=ApiFalsa()), \
             patch.object(agent_main, "JobsChecker", return_value=checker), \
             patch.object(agent_main.sys, "argv", ["main.py", "--fecha", "2026-08-16"]):
            return agent_main.main()


if __name__ == "__main__":
    unittest.main(verbosity=2)
