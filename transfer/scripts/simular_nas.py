"""Prepara la carpeta local que SIMULA el NAS para pruebas sin riesgo (§30).

Crea data/nas_sim (o la ruta dada). Con --limpiar borra su contenido previo
para que cada corrida de prueba empiece desde cero.

Uso:
  python scripts/simular_nas.py
  python scripts/simular_nas.py --limpiar --dir C:\\temp\\nas_sim
"""
import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "nas_sim"


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula el NAS local")
    parser.add_argument("--limpiar", action="store_true", help="Borra el contenido previo")
    parser.add_argument("--dir", help="Carpeta destino (defecto: transfer/data/nas_sim)")
    args = parser.parse_args()

    carpeta = Path(args.dir) if args.dir else DEFAULT_DIR
    if args.limpiar and carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)

    print(f"NAS simulado listo: {carpeta}")
    if args.limpiar:
        print("Contenido previo eliminado (inicio desde cero).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
