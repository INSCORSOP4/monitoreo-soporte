"""Prueba dos fixes del checker:
1. Archivo con fecha ISO en el nombre (DWCalzamoda_2026-08-09.bak) -> debe ACEPTARSE.
2. Artefacto .bak.tmp (copia en curso) -> debe IGNORARSE (no termina en .bak).
"""
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AGENT_ORIGEN_DIR  # noqa: E402

carpeta = Path(AGENT_ORIGEN_DIR) if AGENT_ORIGEN_DIR else Path("data/simulacion")
carpeta.mkdir(parents=True, exist_ok=True)
hoy = date.today()

# 1. DWCalzamoda con fecha ISO en el nombre, mtime en ventana (22:40)
ruta_iso = carpeta / f"DWCalzamoda_{hoy.isoformat()}.bak"
ruta_iso.write_bytes(b"z" * 3_000_000)
mtime = datetime(hoy.year, hoy.month, hoy.day, 22, 40)
os.utime(ruta_iso, (mtime.timestamp(), mtime.timestamp()))
print(f"1. Creado (ISO): {ruta_iso.name} (mtime {mtime.strftime('%H:%M')})")

# 2. PROSUR_PRIME artefacto .bak.tmp con mtime MÁS reciente en la ventana (22:55)
ruta_tmp = carpeta / f"PROSUR_PRIME_{hoy.strftime('%Y%m%d')}_DIF.bak.tmp"
ruta_tmp.write_bytes(b"t" * 500_000)
mtime2 = datetime(hoy.year, hoy.month, hoy.day, 22, 55)
os.utime(ruta_tmp, (mtime2.timestamp(), mtime2.timestamp()))
print(f"2. Creado (tmp): {ruta_tmp.name} (mtime {mtime2.strftime('%H:%M')}) — debe ignorarse")
