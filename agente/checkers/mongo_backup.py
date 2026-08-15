"""Mongo Backup Checker — valida el dump diario de MONGO_BACKUP_DIARIO (§9 Mongo).

Patrón del archivo: backup_YYYYMMDD_HHMM.rar — la fecha Y la hora viajan en el
NOMBRE (a diferencia de SQL, donde la hora sale del mtime del archivo).

Estados:
  OK           -> backup_YYYYMMDD_HHMM.rar dentro de la ventana esperada
                  (23:59 ± 180 min, la que define el catálogo), con tamaño.
  ADVERTENCIA  -> dump de la fecha operativa pero fuera de la ventana
                  (manual/tardío/anticipado).
  ERROR        -> sin dump de la fecha (aunque existan viejos), archivo vacío,
                  o carpeta origen no accesible.

La ventana cruza la medianoche: un dump que corrió a las 00:30 del día siguiente
(backup_20260815_0030.rar para la noche del 14) sigue siendo el respaldo del 14.
Un dump de OTRO día NUNCA cuenta como el de hoy: si solo existen viejos, ERROR.

El estado se reporta al backend; la incidencia automática la crea el backend
cuando el estado es ERROR (§26). El agente NO decide incidencias.
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path


class MongoBackupChecker:
    """Valida la carpeta del dump Mongo contra el horario esperado del día."""

    # backup_20260814_2359.rar (case-insensitive: la fuente Mongo puede variar)
    _PATRON = re.compile(r"^backup_(\d{8})_(\d{4})\.rar$", re.IGNORECASE)

    def __init__(self, origen_override: str = ""):
        # Override para simulación local; en producción la ruta viene del catálogo.
        self._origen_override = origen_override.strip()

    # ------------------------------------------------------------------ helpers

    def _origen_efectivo(self, ruta_origen: str | None) -> str:
        return self._origen_override or ruta_origen or ""

    def _generacion_desde_nombre(self, nombre_archivo: str) -> datetime | None:
        """Devuelve el datetime de generación incrustado en el nombre, o None.

        El patrón fijo es backup_YYYYMMDD_HHMM.rar: si el nombre no calza (otro
        archivo en la carpeta, .tmp a medio escribir, etc.), no es un candidato.
        """
        m = self._PATRON.match(nombre_archivo)
        if not m:
            return None
        try:
            return datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M")
        except ValueError:
            return None

    @staticmethod
    def _ventana(fecha: date, hora: str, tolerancia_minutos: int) -> tuple[datetime, datetime]:
        hh, mm = (int(x) for x in hora.split(":"))
        inicio = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
        return inicio, inicio + timedelta(minutes=tolerancia_minutos)

    @staticmethod
    def _human_bytes(n: int) -> str:
        for unidad in ("B", "KB", "MB", "GB"):
            if n < 1024 or unidad == "GB":
                return f"{n:.1f} {unidad}" if unidad != "B" else f"{n} B"
            n /= 1024
        return f"{n:.1f} GB"

    # -------------------------------------------------------------------- check

    def check(self, base: dict, fecha: date) -> dict:
        """Devuelve el payload de POST /respaldos/ejecuciones para la base."""
        base_id = base["base_datos_id"]
        nombre_base = base["nombre_base"]

        # 1. Horario del día operativo (1=Lun ... 7=Dom). Mongo aplica los 7 días
        #    (DiaAplica=1) con TipoBackupEsperado='FULL', HoraEsperada='23:59'.
        horario = next(
            (h for h in base.get("horarios", []) if h["dia_semana"] == fecha.isoweekday()),
            None,
        )
        if horario is None or not horario["dia_aplica"]:
            return {
                "base_datos_id": base_id,
                "fecha_ejecucion": fecha.isoformat(),
                "estado": "NO_APLICA",
                "detalle": f"Día {fecha.isoweekday()} no aplica para {nombre_base}",
            }

        esperado = horario["tipo_backup_esperado"]  # 'FULL' para Mongo
        carpeta = Path(self._origen_efectivo(base.get("ruta_origen")))

        # 2. Carpeta origen accesible.
        if not carpeta.exists() or not carpeta.is_dir():
            return self._error(base_id, fecha, f"Carpeta origen no accesible: {carpeta}")

        # 3. Candidatos: nombres que calzan backup_YYYYMMDD_HHMM.rar.
        candidatos: list[tuple[datetime, Path]] = []
        for f in carpeta.iterdir():
            if not f.is_file():
                continue
            gen = self._generacion_desde_nombre(f.name)
            if gen is not None:
                candidatos.append((gen, f))
        if not candidatos:
            return self._error(
                base_id, fecha,
                f"No se encontró dump de {nombre_base} (esperado {esperado}) en {carpeta}",
            )

        inicio, fin = self._ventana(fecha, horario["hora_esperada"], horario["tolerancia_minutos"])

        # 3a. Los de la VENTANA esperada son "el dump de la noche" (cubre
        #     medianoche: backup_20260815_0030.rar para la noche del 14).
        en_ventana = [(g, f) for g, f in candidatos if inicio <= g <= fin]
        if en_ventana:
            gen, archivo = max(en_ventana, key=lambda c: c[0])
            fuera_de_horario = False
        else:
            # 3b. Dump de la fecha operativa pero FUERA de la ventana -> ADVERTENCIA.
            #     Dumps de OTROS días NO cuentan como el de hoy -> ERROR (faltante).
            de_hoy = [(g, f) for g, f in candidatos if g.date() == fecha]
            if de_hoy:
                gen, archivo = max(de_hoy, key=lambda c: c[0])
                fuera_de_horario = True
            else:
                return self._error(
                    base_id, fecha,
                    f"No se encontró dump de {nombre_base} para {fecha.isoformat()}: "
                    f"solo existen dumps de otros días en {carpeta}",
                )

        # 4. Tamaño.
        tamano = archivo.stat().st_size
        if tamano <= 0:
            return self._error(base_id, fecha, f"Archivo {archivo.name} está vacío (0 bytes)")

        # 5. Tipo: Mongo es siempre FULL (dump completo diario); el nombre no
        #    trae marcador de tipo, se reporta el esperado del catálogo.
        tipo_encontrado = esperado

        estado = "ADVERTENCIA" if fuera_de_horario else "OK"
        notas = []
        if fuera_de_horario:
            notas.append(f"generado fuera de la ventana {inicio.strftime('%H:%M')}-{fin.strftime('%H:%M')}")
        detalle = (
            f"Archivo: {archivo.name} ({self._human_bytes(tamano)}), "
            f"generado {gen.strftime('%Y-%m-%d %H:%M')}, "
            f"esperado {esperado} a las {horario['hora_esperada']} (tol {horario['tolerancia_minutos']} min). "
            + ("Notas: " + "; ".join(notas) if notas else "Dentro de lo esperado.")
        )

        return {
            "base_datos_id": base_id,
            "fecha_ejecucion": fecha.isoformat(),
            "estado": estado,
            "tipo_backup_encontrado": tipo_encontrado,
            "archivo_encontrado": archivo.name,
            "tamano_bytes": tamano,
            "fecha_generacion": gen.isoformat(sep="T", timespec="seconds"),
            "fuera_de_horario": fuera_de_horario,
            "detalle": detalle,
        }

    def _error(self, base_id: int, fecha: date, motivo: str) -> dict:
        return {
            "base_datos_id": base_id,
            "fecha_ejecucion": fecha.isoformat(),
            "estado": "ERROR",
            "detalle": motivo,
        }
