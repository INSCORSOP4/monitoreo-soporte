"""Pruebas aisladas de generación SQL y parseo CSV del Jobs Checker."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checkers.jobs_checker import JobsChecker, JobsCheckerError  # noqa: E402


class JobsCheckerTest(unittest.TestCase):
    def test_credenciales_vacias_fallan_como_error_del_checker(self) -> None:
        with self.assertRaises(JobsCheckerError):
            JobsChecker("", "").check([{"paso_monitoreado_id": 1}], date(2026, 8, 16))

    def test_consulta_filtra_catalogo_y_escapa_nombre(self) -> None:
        consulta = JobsChecker._consulta(
            [{
                "paso_monitoreado_id": 7,
                "nombre_job": "Carga d'Inventario",
                "step_id": 3,
                "nombre_paso": "Paso 3",
                "horarios": [{"dia_semana": 7, "dia_aplica": True, "hora_esperada": "10:00", "tolerancia_minutos": 30}],
            }],
            date(2026, 8, 16),
        )

        self.assertIn("(7, N'Carga d''Inventario', 3, CAST('10:00' AS time(0)), 30, 1)", consulta)
        self.assertIn("h.run_date = 20260816", consulta)
        self.assertIn("m.PasoMonitoreadoId", consulta)

    def test_csv_genera_ok_error_y_preserva_comas(self) -> None:
        contenido = (
            '"7","Job A","1","10:00:00","Succeeded","2026-08-16T10:01:03","Todo correcto"\n'
            '"8","Job B","2","12:00:00","Failed","2026-08-16T12:03:04","Error, código 5"\n'
            '"9","Job C","3","14:00:00","NotRun","","No se encontró ejecución"\n'
        )
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "resultado.csv"
            ruta.write_text(contenido, encoding="utf-8")
            resultados = JobsChecker._leer_csv(ruta, date(2026, 8, 16))

        self.assertEqual([r["estado"] for r in resultados], ["OK", "ERROR", "PENDIENTE"])
        self.assertEqual(resultados[1]["mensaje"], "Error, código 5")
        self.assertIsNone(resultados[2]["fecha_hora_real"])

    def test_csv_malformado_falla_como_error_del_checker(self) -> None:
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "resultado.csv"
            ruta.write_text('"solo","dos"\n', encoding="utf-8")
            with self.assertRaises(JobsCheckerError):
                JobsChecker._leer_csv(ruta, date(2026, 8, 16))


if __name__ == "__main__":
    unittest.main(verbosity=2)
