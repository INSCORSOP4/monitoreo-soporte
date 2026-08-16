"""Checkers del Agente 10.0.3.8 (Fase 4).

Cada checker valida una fuente y devuelve el payload de
POST /respaldos/ejecuciones. Este proyecto valida SOLO SQL + Mongo:
  - sql_backup.py   : respaldos SQL ({Base}_{fecha}_{TIPO}.bak, §9)
  - mongo_backup.py : dump diario Mongo (backup_YYYYMMDD_HHMM.rar, §9 Mongo)

El checker de Microsip (microsip_backup.py) vive SOLO en agente_6_5/: cada
proyecto de agente trae únicamente los checkers de sus propias fuentes
(§35: nada quemado — main.py despacha con crear_checker según el catálogo).
"""
from checkers.mongo_backup import MongoBackupChecker
from checkers.sql_backup import SqlBackupChecker


def crear_checker(tipo_fuente: str, *, origen_override: str = "", nombres_bases: tuple[str, ...] = ()):
    """Devuelve el checker de la fuente, o None si este proyecto no la valida."""
    if tipo_fuente == "SQL":
        return SqlBackupChecker(origen_override=origen_override, nombres_bases=nombres_bases)
    if tipo_fuente == "MONGO":
        return MongoBackupChecker(origen_override=origen_override)
    return None
