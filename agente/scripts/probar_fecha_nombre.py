"""Prueba la detección de fecha incoherente: archivo con fecha de OTRO día en el
NOMBRE (ej. _20260808_) pero mtime de hoy dentro de la ventana.

El checker debe reportar ADVERTENCIA ('fecha del nombre != fecha operativa')."""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AGENT_ORIGEN_DIR  # noqa: E402

carpeta = Path(AGENT_ORIGEN_DIR) if AGENT_ORIGEN_DIR else Path("data/simulacion")
carpeta.mkdir(parents=True, exist_ok=True)

nombre_base = sys.argv[1] if len(sys.argv) > 1 else "PROSUR_PRIME_DATA"
ayer = date.today() - timedelta(days=1)
nombre = f"{nombre_base}_{ayer.strftime('%Y%m%d')}_DIF.bak"  # fecha de ayer en el nombre
ruta = carpeta / nombre
ruta.write_bytes(b"y" * 2_000_000)

mtime = datetime(date.today().year, date.today().month, date.today().day, 22, 50)  # hoy, dentro de la ventana
os.utime(ruta, (mtime.timestamp(), mtime.timestamp()))
print(f"Archivo creado: {ruta.name}")
print(f"  fecha en el NOMBRE: {ayer} | mtime: {mtime} (hoy, en ventana)")
