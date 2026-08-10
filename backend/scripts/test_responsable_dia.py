"""Prueba del responsable del día: inserta una asignación y verifica que la
incidencia automática la respete (§21, §26)."""
import pyodbc

CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "Trusted_Connection=yes;DATABASE=MONITOREO_SOPORTE;"
    "Encrypt=yes;TrustServerCertificate=no;Command Timeout=0"
)

conn = pyodbc.connect(CONN, timeout=6)
cur = conn.cursor()

# 1. Asignar a Francisco (usuario 2) como responsable del 2026-08-10
cur.execute(
    """
    IF NOT EXISTS (SELECT 1 FROM dbo.responsables_dia WHERE Fecha = CAST('2026-08-10' AS DATE))
        INSERT INTO dbo.responsables_dia (Fecha, UsuarioId, OrigenAsignacion) VALUES (CAST('2026-08-10' AS DATE), 2, 'AUTO')
    """
)
conn.commit()

# 2. Mostrar el estado
print("=== responsables_dia (2026-08-10) ===")
cur.execute("SELECT ResponsableDiaId, Fecha, UsuarioId, OrigenAsignacion FROM dbo.responsables_dia")
for r in cur.fetchall():
    print(" ", r[0], "|", r[1], "| usuario:", r[2], "|", r[3])

conn.close()
print("OK")
