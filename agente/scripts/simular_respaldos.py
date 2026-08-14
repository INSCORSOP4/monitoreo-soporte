"""Genera archivos .bak FALSOS en una carpeta local para SIMULAR G:\\TempRespSQLServer.

El catálogo de bases se lee del backend (mismo endpoint que usa el agente), así
la simulación siempre está alineada con la configuración real (§35).

Uso:
  python scripts/simular_respaldos.py
  python scripts/simular_respaldos.py --omitir DWCalzamoda            # simula faltante -> ERROR
  python scripts/simular_respaldos.py --atrasado PROSUR_PRIME_BLINK   # mtime fuera de ventana -> ADVERTENCIA
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
    bases = [b for b in configuracion["bases"] if b["tipo_fuente"] == "SQL"]
    if not bases:
        print("No hay bases SQL en el catálogo del backend.")
        return 2

    # Limpia .bak previos: corridas con fechas distintas no deben acumular
    # archivos viejos que confundan al checker (falso ADVERTENCIA/OK).
    carpeta.mkdir(parents=True, exist_ok=True)
    viejos = list(carpeta.glob("*.bak"))
    for viejo in viejos:
        viejo.unlink()
    if viejos:
        print(f"Limpios {len(viejos)} archivos .bak previos de {carpeta}\n")
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
        sufijo_tipo = "DIF" if tipo == "DIFERENCIAL" else "FULL"
        nombre_archivo = f"{nombre}_{fecha.strftime('%Y%m%d')}_{sufijo_tipo}.bak"
        ruta = carpeta / nombre_archivo

        ruta.write_bytes(os.urandom(random.randint(1_000_000, 5_000_000)))  # 1-5 MB falsos

        if nombre.upper() in atrasados:
            mtime = datetime(fecha.year, fecha.month, fecha.day, 9, 0)  # fuera de la ventana (22:00±3h)
            marca = "FUERA de ventana (09:00) -> ADVERTENCIA"
        else:
            mtime = datetime(fecha.year, fecha.month, fecha.day, 22, 5)  # dentro de la ventana -> OK
            marca = "dentro de ventana (22:05) -> OK"
        os.utime(ruta, (mtime.timestamp(), mtime.timestamp()))

        print(f"  [creado] {nombre_archivo}  ({ruta.stat().st_size // 1024} KB, {marca})")
        creados += 1

    print(f"\n{creados} archivos simulados. Omitidos: {omitir or '(ninguno)'} | Atrasados: {atrasados or '(ninguno)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
