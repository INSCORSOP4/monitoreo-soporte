"""SQL Backup Checker (§9) — valida la carpeta origen contra el catálogo esperado.

Por base SQL decide el estado de la ejecución diaria:
  OK           -> archivo de la fecha dentro de la ventana esperada, con tamaño.
  ADVERTENCIA  -> archivo de la fecha operativa pero fuera de horario, o tipo
                  distinto al esperado, o FECHA DEL NOMBRE distinta a la operativa.
  ERROR        -> sin archivo de la fecha (aunque existan viejos), archivo vacío,
                  o carpeta origen no accesible.
  NO_APLICA    -> el día operativo no aplica para la base (ej. Mercaltos domingo).

IMPORTANTE: un respaldo de OTRO día (archivo viejo) NUNCA cuenta como el de hoy:
si solo existen archivos viejos, el estado es ERROR (faltante).

El estado se reporta al backend; la incidencia automática la crea el backend
cuando el estado es ERROR (§26). El agente NO decide incidencias.
"""
import re
from datetime import date, datetime, timedelta
from pathlib import Path


class SqlBackupChecker:
    def __init__(
        self,
        origen_override: str = "",
        sufijos: tuple[str, ...] = (".bak",),
        nombres_bases: tuple[str, ...] = (),
    ):
        # Override para simulación local; en producción la ruta viene del catálogo.
        self._origen_override = origen_override.strip()
        self._sufijos = tuple(s.lower() for s in sufijos if s) or (".bak",)
        # Nombres de TODAS las bases validadas (sin repetir): sirven para resolver
        # colisiones de prefijo — PROSUR_PRIME no debe capturar archivos de
        # PROSUR_PRIME_DATA/BLINK aunque "empiecen" con el mismo nombre.
        self._nombres_bases = tuple(dict.fromkeys(n.lower() for n in nombres_bases))

    # ------------------------------------------------------------------ helpers

    def _origen_efectivo(self, ruta_origen: str | None) -> str:
        return self._origen_override or ruta_origen or ""

    def _coincide(self, nombre_archivo: str, nombre_base: str) -> bool:
        """¿El archivo es un respaldo de ESTA base?

        - Debe empezar con el nombre de la base y terminar con un sufijo de
          respaldo (.bak) — excluye artefactos tipo .bak.tmp o sin extensión.
        - Colisión de prefijos: si el archivo también matchea una base MÁS
          LARGA (ej. PROSUR_PRIME_DATA para la base PROSUR_PRIME), no es de esta.
          Nombres reales con cualquier formato tras el prefijo (fecha ISO,
          _manual, etc.) se aceptan: el mtime y la fecha del nombre validan.
        """
        nombre = nombre_archivo.lower()
        prefijo = nombre_base.lower()
        if not nombre.startswith(prefijo):
            return False
        if not any(nombre.endswith(suf) for suf in self._sufijos):
            return False
        for otra in self._nombres_bases:
            if len(otra) > len(prefijo) and nombre.startswith(otra):
                return False
        return True

    _TIPO_RE = re.compile(r"_(FULL|DIFERENCIAL|DIF)(?:[_.\-]|$)", re.IGNORECASE)
    _FECHA_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")  # YYYYMMDD aislado

    def _tipo_desde_nombre(self, nombre_archivo: str, esperado: str) -> str:
        """Tipo según el MARCADOR del archivo (ej. ..._DIF.bak), no del nombre de la base.

        Si el nombre de la base contuviera 'DIF'/'FULL' (ej. DIFSA), el prefijo no
        debe influir: solo el sufijo '_FULL.'/'_DIF.' decide.
        """
        m = self._TIPO_RE.search(nombre_archivo)
        if m:
            return "FULL" if m.group(1).upper() == "FULL" else "DIFERENCIAL"
        return esperado  # sin marca de tipo: se asume el esperado

    def _fecha_desde_nombre(self, nombre_archivo: str, nombre_base: str) -> date | None:
        """Fecha YYYYMMDD incrustada en el nombre (si la trae), tras el prefijo de la base.

        Ej. 'DWCalzamoda_20260809_DIF.bak' -> 2026-08-09. Devuelve None si no hay
        fecha o no es una fecha válida (algunos respaldos no la incluyen; ahí el
        mtime es la fuente de verdad). Buscar solo tras el prefijo evita que un
        nombre de base con 8 dígitos contamine la detección.
        """
        resto = nombre_archivo[len(nombre_base):]
        m = self._FECHA_RE.search(resto)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
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

        # 1. Horario del día operativo (1=Lun ... 7=Dom, igual que la BD).
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

        esperado = horario["tipo_backup_esperado"]
        carpeta = Path(self._origen_efectivo(base.get("ruta_origen")))

        # 2. Carpeta origen accesible.
        if not carpeta.exists() or not carpeta.is_dir():
            return self._error(base_id, fecha, f"Carpeta origen no accesible: {carpeta}")

        # 3. Buscar archivos del respaldo (prefijo del nombre + sufijo .bak).
        candidatos = [
            f for f in carpeta.iterdir()
            if f.is_file() and self._coincide(f.name, nombre_base)
        ]
        if not candidatos:
            return self._error(
                base_id, fecha,
                f"No se encontró respaldo de {nombre_base} (esperado {esperado}) en {carpeta}",
            )

        inicio, fin = self._ventana(fecha, horario["hora_esperada"], horario["tolerancia_minutos"])

        # 3a. Los de la VENTANA esperada son "el respaldo de la noche" (cubre
        #     medianoche: un archivo a las 00:30 del día siguiente cae en la ventana).
        en_ventana = [f for f in candidatos if inicio <= datetime.fromtimestamp(f.stat().st_mtime) <= fin]
        if en_ventana:
            archivo = max(en_ventana, key=lambda f: f.stat().st_mtime)
            fuera_de_horario = False
        else:
            # 3b. Archivo de la fecha operativa pero FUERA de la ventana
            #     (manual/tardío/anticipado) -> ADVERTENCIA. Los archivos de OTROS
            #     días NO cuentan como el respaldo de hoy -> ERROR (faltante).
            de_hoy = [f for f in candidatos if datetime.fromtimestamp(f.stat().st_mtime).date() == fecha]
            if de_hoy:
                archivo = max(de_hoy, key=lambda f: f.stat().st_mtime)
                fuera_de_horario = True
            else:
                return self._error(
                    base_id, fecha,
                    f"No se encontró respaldo de {nombre_base} para {fecha.isoformat()}: "
                    f"solo existen archivos de otros días en {carpeta}",
                )

        # 4. Tamaño.
        tamano = archivo.stat().st_size
        if tamano <= 0:
            return self._error(base_id, fecha, f"Archivo {archivo.name} está vacío (0 bytes)")

        # 5. Tipo esperado vs encontrado + fecha incrustada en el NOMBRE (§9).
        tipo_encontrado = self._tipo_desde_nombre(archivo.name, esperado)
        fecha_generacion = datetime.fromtimestamp(archivo.stat().st_mtime)
        tipo_incorrecto = tipo_encontrado != esperado
        fecha_en_nombre = self._fecha_desde_nombre(archivo.name, nombre_base)
        fecha_incoherente = fecha_en_nombre is not None and fecha_en_nombre != fecha

        estado = "ADVERTENCIA" if (fuera_de_horario or tipo_incorrecto or fecha_incoherente) else "OK"
        notas = []
        if fuera_de_horario:
            notas.append(f"generado fuera de la ventana {inicio.strftime('%H:%M')}-{fin.strftime('%H:%M')}")
        if tipo_incorrecto:
            notas.append(f"tipo {tipo_encontrado} != esperado {esperado}")
        if fecha_incoherente:
            notas.append(
                f"fecha del nombre ({fecha_en_nombre.isoformat()}) != fecha operativa ({fecha.isoformat()})"
            )
        detalle = (
            f"Archivo: {archivo.name} ({self._human_bytes(tamano)}), "
            f"generado {fecha_generacion.strftime('%Y-%m-%d %H:%M')}, "
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
            "fecha_generacion": fecha_generacion.isoformat(sep="T", timespec="seconds"),
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
