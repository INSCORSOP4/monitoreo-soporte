"""Aplica los índices únicos filtrados de incidencias (§26) a LocalDB y los verifica."""
import pyodbc

CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "Trusted_Connection=yes;DATABASE=MONITOREO_SOPORTE;"
    "Encrypt=yes;TrustServerCertificate=no;Command Timeout=0"
)

conn = pyodbc.connect(CONN, timeout=6)
cur = conn.cursor()

cur.execute(
    """
    IF NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'UQ_incidencias_SISTEMA_Abierta' AND object_id = OBJECT_ID(N'dbo.incidencias'))
        CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_SISTEMA_Abierta
            ON dbo.incidencias (BaseDatosId, FechaIncidencia, DetectadaPor)
            WHERE DetectadaPor = 'SISTEMA' AND Estado = 'ABIERTA';
    """
)
cur.execute(
    """
    IF NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'UQ_incidencias_SISTEMA_EnProceso' AND object_id = OBJECT_ID(N'dbo.incidencias'))
        CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_SISTEMA_EnProceso
            ON dbo.incidencias (BaseDatosId, FechaIncidencia, DetectadaPor)
            WHERE DetectadaPor = 'SISTEMA' AND Estado = 'EN_PROCESO';
    """
)
conn.commit()

cur.execute(
    """
    SELECT i.name, i.is_unique, i.filter_definition
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'dbo.incidencias') AND i.name LIKE 'UQ_incidencias_SISTEMA%'
    """
)
print("=== Índices únicos filtrados de incidencias ===")
for r in cur.fetchall():
    print(" ", r[0], "| unique:", r[1], "| filtro:", r[2])

conn.close()
print("OK")
