"""SOLO PRUEBAS — limpia la tabla transferencias de la BD local.

Permite repetir escenarios (dry-run -> real -> fallida) sobre la misma fecha
sin que el filtro 'sin transferencia COMPLETADA' bloquee la re-ejecución.

Conecta con pyodbc usando la misma cadena que el backend (.env del backend).
Uso:
  python monitoreo-soporte/transfer/scripts/limpiar_transferencias.py          # borra TODO
  python monitoreo-soporte/transfer/scripts/limpiar_transferencias.py 1 2      # solo ejecuciones 1 y 2

¡NUNCA ejecutar contra una base que no sea la de desarrollo!
"""
import sys
from pathlib import Path

# Backend: app.core.database puede no estar montado; leemos el .env directo.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"


def _connection_string() -> str:
    texto = (_BACKEND / ".env").read_text(encoding="utf-8")
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("DATABASE_URL="):
            return linea.partition("=")[2].strip().strip('"').strip("'")
    raise SystemExit("DATABASE_URL no está en monitoreo-soporte/backend/.env")


def main() -> int:
    import pyodbc

    ejecuciones = [int(x) for x in sys.argv[1:]]
    conn = pyodbc.connect(_connection_string(), timeout=6)
    cur = conn.cursor()
    if ejecuciones:
        cur.execute(
            f"DELETE FROM transferencias WHERE EjecucionId IN ({','.join('?' * len(ejecuciones))})",
            *ejecuciones,
        )
        print(f"Borradas transferencias de {len(ejecuciones)} ejecuciones: {ejecuciones}")
    else:
        filas = cur.execute("SELECT COUNT(*) FROM transferencias").fetchone()[0]
        cur.execute("DELETE FROM transferencias")
        print(f"Borradas TODAS las transferencias ({filas} filas)")
    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
