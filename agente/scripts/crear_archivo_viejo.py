"""Prueba del fix de archivos viejos: crea un .bak de AYER para una base.

El SQL Backup Checker NO debe contarlo como el respaldo de HOY → ERROR (faltante).
"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AGENT_ORIGEN_DIR  # noqa: E402

carpeta = Path(AGENT_ORIGEN_DIR) if AGENT_ORIGEN_DIR else Path("data/simulacion")
carpeta.mkdir(parents=True, exist_ok=True)

nombre_base = sys.argv[1] if len(sys.argv) > 1 else "DWCalzamoda"
ayer = date.today() - timedelta(days=1)
nombre = f"{nombre_base}_{ayer.strftime('%Y%m%d')}_FULL.bak"
ruta = carpeta / nombre
ruta.write_bytes(b"x" * 2_000_000)

mtime = datetime(ayer.year, ayer.month, ayer.day, 22, 5)
os.utime(ruta, (mtime.timestamp(), mtime.timestamp()))
print(f"Archivo VIEJO creado: {ruta} (mtime {mtime})")
