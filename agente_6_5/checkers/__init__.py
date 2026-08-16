"""Checkers del Agente 192.168.6.5 (Fase 4, §10).

Cada checker valida una fuente y devuelve el payload de
POST /respaldos/ejecuciones. Este proyecto valida SOLO Microsip:
  - microsip_backup.py : .7z diario de Microsip (Microsip_Backups_YYYYMMDD_HHMMSS.7z, §10)

Los checkers SQL y Mongo (sql_backup.py, mongo_backup.py) viven SOLO en
agente/: cada proyecto de agente trae únicamente los checkers de sus propias
fuentes (§35: nada quemado — main.py despacha con crear_checker según el
catálogo). Cuando exista el checker de Mercaltos, se registra aquí.
"""
from checkers.microsip_backup import MicrosipBackupChecker


def crear_checker(tipo_fuente: str, *, origen_override: str = "", nombres_bases: tuple[str, ...] = ()):
    """Devuelve el checker de la fuente, o None si este proyecto no la valida."""
    if tipo_fuente == "MICROSIP":
        return MicrosipBackupChecker(origen_override=origen_override)
    return None
