"""Checkers del Agente 10.0.3.8 (Fase 4).

Cada checker valida una fuente y devuelve el payload de
POST /respaldos/ejecuciones. Por ahora:
  - sql_backup.py   : respaldos SQL ({Base}_{fecha}_{TIPO}.bak, §9)
  - mongo_backup.py : dump diario Mongo (backup_YYYYMMDD_HHMM.rar, §9 Mongo)
"""
