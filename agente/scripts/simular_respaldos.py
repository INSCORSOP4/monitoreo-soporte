"""Genera archivos FALSOS en una carpeta local para SIMULAR las carpetas origen:
- SQL:   {Base}_{YYYYMMDD}_{DIF|FULL}.bak  (simula G:\\TempRespSQLServer)
- MONGO: backup_{YYYYMMDD}_{HHMM}.rar      (simula G:\\BackupMongo\\BackupMongoTemp)

El catálogo de bases se lee del backend (mismo endpoint que usa el agente), así
la simulación siempre está alineada con la configuración real (§35).

Uso:
  python scripts/simular_respaldos.py
  python scripts/simular_respaldos.py --omitir DWCalzamoda            # simula faltante -> ERROR
  python scripts/simular_respaldos.py --atrasado PROSUR_PRIME_BLINK   # mtime fuera de ventana -> ADVERTENCIA
  python scripts/simular_respaldos.py --omitir MONGO_BACKUP_DIARIO    # dump Mongo faltante -> ERROR
  python scripts/simular_respaldos.py --atrasado MONGO_BACKUP_DIARIO  # dump Mongo fuera de hora -> ADVERTENCIA
  python scripts/simular_respaldos.py --fecha 2026-08-11 --dir C:\\temp\\sim
"""
import argparse
import os
import random
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api_client import ApiClient  # noqa: E402
from config import AGENT_API_KEY, API_BASE_URL  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "simulacion"


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula respaldos .bak locales")
    parser.add_argument("--omitir", help="Bases (coma) que NO se generan -> simulan faltante")
    parser.add_argument("--atrasado", help="Bases (coma) cuyo archivo queda FUERA de la ventana")
    parser.add_argument("--fecha", help="Fecha operativa YYYY-MM-DD (defecto: hoy)")
    parser.add_argument("--dir", help="Carpeta destino (defecto: agente/data/simulacion)")
    args = parser.parse_args()

    fecha = date.fromisoformat(args.fecha) if args.fecha else date.today()
    carpeta = Path(args.dir) if args.dir else DEFAULT_DIR
    omitir = {x.strip().upper() for x in (args.omitir or "").split(",") if x.strip()}
    atrasados = {x.strip().upper() for x in (args.atrasado or "").split(",") if x.strip()}

    api = ApiClient(API_BASE_URL, AGENT_API_KEY)
    configuracion = api.get_configuracion()
    bases = [b for b in configuracion["bases"] if b["tipo_fuente"] in ("SQL", "MONGO")]
    if not bases:
        print("No hay bases SQL/MONGO en el catálogo del backend.")
        return 2

    # Limpia .bak/.rar previos: corridas con fechas distintas no deben acumular
    # archivos viejos que confundan al checker (falso ADVERTENCIA/OK).
    carpeta.mkdir(parents=True, exist_ok=True)
    viejos = list(carpeta.glob("*.bak")) + list(carpeta.glob("*.rar"))
    for viejo in viejos:
        viejo.unlink()
    if viejos:
        print(f"Limpios {len(viejos)} archivos .bak/.rar previos de {carpeta}\n")
    creados = 0
    print(f"Simulando respaldos de {fecha.isoformat()} en {carpeta}\n")
    for base in bases:
        nombre = base["nombre_base"]
        if nombre.upper() in omitir:
            print(f"  [OMITIDO] {nombre}  (simula faltante)")
            continue

        horario = next(
            (h for h in base.get("horarios", []) if h["dia_semana"] == fecha.isoweekday()),
            None,
        )
        tipo = horario["tipo_backup_esperado"] if horario else base["tipo_backup_predeterminado"]
        atrasada = nombre.upper() in atrasados

        if base["tipo_fuente"] == "MONGO":
            # Patrón Mongo: backup_YYYYMMDD_HHMM.rar — la hora va en el NOMBRE,
            # no en el mtime. El dump esperado es a la HoraEsperada (23:59).
            hhmm = "0900" if atrasada else (horario["hora_esperada"].replace(":", "") if horario else "2359")
            nombre_archivo = f"backup_{fecha.strftime('%Y%m%d')}_{hhmm}.rar"
            mtime = datetime(fecha.year, fecha.month, fecha.day, int(hhmm[:2]), int(hhmm[2:]))
        else:
            sufijo_tipo = "DIF" if tipo == "DIFERENCIAL" else "FULL"
            nombre_archivo = f"{nombre}_{fecha.strftime('%Y%m%d')}_{sufijo_tipo}.bak"
            # SQL: el mtime lleva la hora de generación (09:00 atrasado, 22:05 OK).
            mtime = datetime(fecha.year, fecha.month, fecha.day, 9, 0) if atrasada else datetime(fecha.year, fecha.month, fecha.day, 22, 5)
        ruta = carpeta / nombre_archivo

        ruta.write_bytes(os.urandom(random.randint(1_000_000, 5_000_000)))  # 1-5 MB falsos
        os.utime(ruta, (mtime.timestamp(), mtime.timestamp()))

        marca = "FUERA de ventana -> ADVERTENCIA" if atrasada else "dentro de ventana -> OK"
        print(f"  [creado] {nombre_archivo}  ({ruta.stat().st_size // 1024} KB, {marca})")
        creados += 1

    print(f"\n{creados} archivos simulados. Omitidos: {omitir or '(ninguno)'} | Atrasados: {atrasados or '(ninguno)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
