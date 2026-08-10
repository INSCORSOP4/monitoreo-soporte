"""Verifica que la incidencia automática quedó vinculada al responsable del día."""
import pyodbc

CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "Trusted_Connection=yes;DATABASE=MONITOREO_SOPORTE;"
    "Encrypt=yes;TrustServerCertificate=no;Command Timeout=0"
)

conn = pyodbc.connect(CONN, timeout=6)
cur = conn.cursor()

print("=== incidencias ===")
cur.execute(
    """
    SELECT i.IncidenciaId, i.TipoIncidenciaId, t.Codigo, i.BaseDatosId, b.NombreBase,
           i.FechaIncidencia, i.Estado, i.DetectadaPor, i.ResponsableDiaId, u.NombreCompleto
    FROM dbo.incidencias i
    LEFT JOIN dbo.cat_tipos_incidencia t ON t.TipoIncidenciaId = i.TipoIncidenciaId
    LEFT JOIN dbo.cat_bases_datos b ON b.BaseDatosId = i.BaseDatosId
    LEFT JOIN dbo.cat_usuarios u ON u.UsuarioId = i.ResponsableDiaId
    ORDER BY i.IncidenciaId
    """
)
for r in cur.fetchall():
    print(" ", r[0], "| tipo:", r[2], "| base:", r[3], r[4], "|", r[5], "|", r[6], "|", r[7], "| resp:", r[8], r[9])

conn.close()
print("OK")
