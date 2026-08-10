"""Diagnóstico de conexión a MONITOREO_SOPORTE (LocalDB).

Uso: python scripts/test_connection.py
Prueba la connection string tal como está configurada en el .env.
"""
import sys
from pathlib import Path

# Permite ejecutar desde backend/ o desde scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


def main() -> None:
    print("=== Connection string usada ===")
    # Ocultar la contraseña al imprimir
    url = settings.database_url
    print(url[:url.find("PWD") + 3] + "***" if "PWD" in url else url)

    from sqlalchemy import text

    from app.core.database import engine

    print("\n=== Intentando conexión (timeout 10s) ===")
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT DB_NAME(), @@VERSION")).fetchone()
            print("CONEXION_OK")
            print("Base actual :", row[0])
            print("SQL Server  :", row[1][:80])
    except Exception as exc:  # noqa: BLE001
        print("ERROR:", type(exc).__name__)
        print(str(exc)[:500])


if __name__ == "__main__":
    main()
