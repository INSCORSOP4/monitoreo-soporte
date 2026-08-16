"""Mercaltos Backup Checker — valida el .7z diario de MERCALTOS_BACKUP_DIARIO (§10).

Patrón del archivo: 'RESPALDOS_MERCALTOS YYYY-MM-DD HH;MM;SS.7z' — a diferencia
de los demás checkers, este usa ESPACIOS (no _) entre partes y ';' (no ':')
dentro de la hora. La fecha Y la hora viajan en el NOMBRE (es el .7z externo,
confiable, igual que Microsip). No se abre el contenido del .7z.

Específico de Mercaltos:
  - La carpeta origen es H:\\Mi unidad\\Comercialtos\\Respaldos: H:\\ es la
    unidad de Google Drive de escritorio. ANTES de buscar el archivo se verifica
    que la unidad H:\\ exista y sea accesible; si no, el ERROR dice
    'Unidad H:\\ no accesible (Google Drive no montado)' — así Soporte sabe de
    inmediato si es problema de Drive y no del respaldo en sí.
  - Mercaltos NO corre domingo (DiaAplica=0) -> NO_APLICA ese día.

Estados:
  OK           -> RESPALDOS_MERCALTOS YYYY-MM-DD HH;MM;SS.7z dentro de la ventana
                  esperada (17:36 ± 180 min = 14:36-20:36, NO cruza medianoche).
  ADVERTENCIA  -> .7z de la fecha operativa pero fuera de la ventana.
  ERROR        -> sin .7z de la fecha (aunque existan viejos), archivo vacío,
                  o la unidad H:\\ / carpeta origen no accesible.
  NO_APLICA    -> domingo (el día no aplica para Mercaltos).

El estado se reporta al backend; la incidencia automática la crea el backend
cuando el estado es ERROR (§26). El agente NO decide incidencias.
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path


class MercaltosBackupChecker:
    """Valida la carpeta del .7z Mercaltos contra el horario esperado del día."""

    # 'RESPALDOS_MERCALTOS 2026-08-15 17;36;22.7z' — espacios entre partes y
    # ';' en la hora (case-insensitive: la fuente puede variar).
    _PATRON = re.compile(r"^RESPALDOS_MERCALTOS (\d{4})-(\d{2})-(\d{2}) (\d{2});(\d{2});(\d{2})\.7z$", re.IGNORECASE)

    # Ventana simétrica: HoraEsperada ± ToleranciaMinutos (14:36-20:36 para
    # 17:36 ± 180, NO cruza medianoche). Ver _ventana().

    def __init__(self, origen_override: str = ""):
        # Override para simulación local; en producción la ruta viene del catálogo.
        self._origen_override = origen_override.strip()

    # ------------------------------------------------------------------ helpers

    def _origen_efectivo(self, ruta_origen: str | None) -> str:
        return self._origen_override or ruta_origen or ""

    def _generacion_desde_nombre(self, nombre_archivo: str) -> datetime | None:
        """Devuelve el datetime de generación incrustado en el nombre, o None.

        El patrón fijo es 'RESPALDOS_MERCALTOS YYYY-MM-DD HH;MM;SS.7z': si el
        nombre no calza (otro archivo en la carpeta, .tmp a medio escribir,
        etc.), no es un candidato.
        """
        m = self._PATRON.match(nombre_archivo)
        if not m:
            return None
        try:
            return datetime.strptime(
                f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}",
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            return None

    @staticmethod
    def _ventana(fecha: date, hora: str, tolerancia_minutos: int) -> tuple[datetime, datetime]:
        """Ventana SIMÉTRICA alrededor de la hora esperada (§10 Mercaltos).

        HoraEsperada 17:36 + tol 180 -> ventana 14:36-20:36 (NO cruza la
        medianoche). Un .7z generado antes (ej. 15:00) o después (ej. 19:30)
        de la hora esperada es válido dentro de la ventana.
        """
        hh, mm = (int(x) for x in hora.split(":"))
        centro = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
        return centro - timedelta(minutes=tolerancia_minutos), centro + timedelta(minutes=tolerancia_minutos)

    @staticmethod
    def _unidad_no_accesible(carpeta: Path) -> bool:
        """¿La unidad raíz de la carpeta no está montada?

        En Windows, Path('H:\\\\').exists() devuelve False si la unidad no
        existe (Google Drive desmontado). En Linux/otro (solo pruebas) no se
        aplica: se devuelve False y cae en el error genérico de carpeta.
        """
        if not carpeta.drive:  # sin letra de unidad (ej. ruta relativa/override POSIX)
            return False
        try:
            return not Path(f"{carpeta.drive}\\").exists()
        except OSError:
            return False

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

        # 1. Horario del día operativo (1=Lun ... 7=Dom). Mercaltos aplica
        #    Lun-Sáb (DiaAplica=1) con FULL, 17:36, tol 180; domingo NO aplica.
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

        esperado = horario["tipo_backup_esperado"]  # 'FULL' para Mercaltos
        carpeta = Path(self._origen_efectivo(base.get("ruta_origen")))

        # 2. Accesibilidad ANTES de buscar el archivo (§30: no operar sobre una
        #    unidad caída). H:\\ es Google Drive: si la unidad no está montada,
        #    el mensaje lo dice explícito para que Soporte no investigue el
        #    respaldo cuando el problema es Drive.
        if not carpeta.exists() or not carpeta.is_dir():
            if self._unidad_no_accesible(carpeta):
                return self._error(base_id, fecha, "Unidad H:\\ no accesible (Google Drive no montado)")
            return self._error(base_id, fecha, f"Carpeta origen no accesible: {carpeta}")

        # 3. Candidatos: nombres que calzan RESPALDOS_MERCALTOS YYYY-MM-DD HH;MM;SS.7z.
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
                f"No se encontró respaldo de {nombre_base} (esperado {esperado}) en {carpeta}",
            )

        inicio, fin = self._ventana(fecha, horario["hora_esperada"], horario["tolerancia_minutos"])

        # 3a. Los de la VENTANA esperada son "el respaldo de la noche".
        en_ventana = [(g, f) for g, f in candidatos if inicio <= g <= fin]
        if en_ventana:
            gen, archivo = max(en_ventana, key=lambda c: c[0])
            fuera_de_horario = False
        else:
            # 3b. .7z de la fecha operativa pero FUERA de la ventana -> ADVERTENCIA.
            #     .7z de OTROS días NO cuentan como el de hoy -> ERROR (faltante).
            de_hoy = [(g, f) for g, f in candidatos if g.date() == fecha]
            if de_hoy:
                gen, archivo = max(de_hoy, key=lambda c: c[0])
                fuera_de_horario = True
            else:
                return self._error(
                    base_id, fecha,
                    f"No se encontró respaldo de {nombre_base} para {fecha.isoformat()}: "
                    f"solo existen .7z de otros días en {carpeta}",
                )

        # 4. Tamaño.
        tamano = archivo.stat().st_size
        if tamano <= 0:
            return self._error(base_id, fecha, f"Archivo {archivo.name} está vacío (0 bytes)")

        # 5. Tipo: Mercaltos es siempre FULL (un archivo diario); el nombre no
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
