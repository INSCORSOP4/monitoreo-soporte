"""Rota la API key del agente AGENTE_10.0.3.8 (AgenteId=1) al formato
'<AgenteId>.<secreto>' y actualiza su ApiKeyHash (bcrypt del secreto).

IMPORTANTE: imprime la nueva key EN CLARO una sola vez — guárdala.
"""
import sys

import pyodbc

sys.path.insert(0, ".")
from app.core.security import compose_api_key, generate_secreto, hash_api_key  # noqa: E402

CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "Trusted_Connection=yes;DATABASE=MONITOREO_SOPORTE;"
    "Encrypt=yes;TrustServerCertificate=no;Command Timeout=0"
)

AGENTE_ID = 1
NOMBRE = "AGENTE_10.0.3.8"

conn = pyodbc.connect(CONN, timeout=6)
cur = conn.cursor()

cur.execute("SELECT AgenteId, Nombre FROM dbo.cat_agentes WHERE AgenteId = ?", AGENTE_ID)
row = cur.fetchone()
if row is None:
    print(f"ERROR: no existe el agente {AGENTE_ID}")
    sys.exit(1)

secreto = generate_secreto()
nueva_key = compose_api_key(AGENTE_ID, secreto)

cur.execute(
    "UPDATE dbo.cat_agentes SET ApiKeyHash = ? WHERE AgenteId = ?",
    hash_api_key(secreto),
    AGENTE_ID,
)
conn.commit()

print("=== API key rotada al nuevo formato <AgenteId>.<secreto> ===")
print(f"  Agente: {row[1]} (id={AGENTE_ID})")
print()
print("  NUEVA API KEY (guárdala, solo se muestra una vez):")
print(f"  {nueva_key}")
print()
print("  En BD solo queda el hash bcrypt del secreto.")

conn.close()
