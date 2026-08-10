"""Prueba pyodbc a LocalDB con autenticación de Windows.

Uso: python scripts/test_pyodbc_raw.py
"""
import pyodbc

conn_str = (
    r"DRIVER={ODBC Driver 18 for SQL Server};"
    r"SERVER=(localdb)\MSSQLLocalDB;"
    r"Trusted_Connection=yes;"
    r"DATABASE=MONITOREO_SOPORTE;"
    r"Encrypt=yes;"
    r"TrustServerCertificate=no;"
    r"Command Timeout=0"
)

print("=== pyodbc -> MONITOREO_SOPORTE (Windows auth) ===")
try:
    conn = pyodbc.connect(conn_str, timeout=6)
    cur = conn.cursor()
    cur.execute("SELECT DB_NAME()")
    print("  Conectado a:", cur.fetchone()[0])
    cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' ORDER BY TABLE_NAME")
    tablas = [r[0] for r in cur.fetchall()]
    print(f"  Tablas dbo ({len(tablas)}):", tablas)
    conn.close()
except Exception as exc:  # noqa: BLE001
    print("  ERROR:", str(exc)[:250])
