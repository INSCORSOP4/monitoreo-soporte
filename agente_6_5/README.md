# Agente 192.168.6.5 — Microsip Backup Checker (Fase 4, §10)

Agente **independiente** del backend y de `agente/` (se ejecutará en el servidor
192.168.6.5 vía Task Scheduler). Valida el respaldo diario de Microsip
(`MICROSIP_BACKUP_DIARIO`, empaquetado `.7z`) contra el catálogo del sistema y
reporta el resultado; el backend decide las incidencias (§26).

**Solo biblioteca estándar de Python 3.11+** — no requiere `pip install` en el
servidor (urllib, json, logging, pathlib, datetime).

## ¿Qué hace?

```
1. Lee su configuración del backend  GET /api/v1/ingesta/configuracion (X-Agent-Key)
   → bases de su grupo, ruta origen, horarios esperados por día (§35: nada quemado).
2. Para cada base MICROSIP valida la carpeta origen (D:\Respaldos_Microsip\Local):
   - ¿existe el .7z de respaldo? (patrón Microsip_Backups_YYYYMMDD_HHMMSS.7z)
   - ¿tamaño > 0?
   - ¿dentro de la ventana esperada? (22:00 ± 180 = 19:00-01:00, ventana SIMÉTRICA
     que cruza la medianoche — cubre el caso real de un .7z generado a las 00:32)
3. Reporta cada base          POST /api/v1/respaldos/ejecuciones (idempotente)
   - OK            -> .7z correcto y a tiempo
   - ADVERTENCIA   -> .7z del día pero fuera de la ventana
   - ERROR         -> sin .7z de HOY (aunque existan viejos) / vacío / carpeta no accesible
   - NO_APLICA     -> el día no aplica
   El backend crea la incidencia automática (DetectadaPor=SISTEMA) si hay ERROR.
```

La fecha del nombre del `.7z` SÍ es confiable (es el `.7z` externo que empaqueta
los `.fbk` internos, que traen fecha fija): por eso la hora de generación se lee
del NOMBRE, no del mtime. No se abre el contenido del `.7z` (validación del
archivo completo, igual que el checker de Mongo).

## Estructura

```
agente_6_5/
├── main.py                  # Orquesta: config → validar → reportar (IDÉNTICO a agente/)
├── config.py                # Variables de entorno + .env (IDÉNTICO a agente/)
├── logger.py                # Logging estructurado (§35) (IDÉNTICO a agente/)
├── api_client.py            # Cliente HTTP (urllib, reintentos §13) (IDÉNTICO a agente/)
├── checkers/
│   ├── __init__.py          # Factory crear_checker() — ESTE proyecto: MICROSIP + MERCALTOS
│   ├── microsip_backup.py   # Checker Microsip (§10)
│   └── mercaltos_backup.py  # Checker Mercaltos (§10) — patrón con espacios y ';',
│                            #   verifica accesibilidad de H:\ (Google Drive)
├── scripts/
│   └── simular_respaldos.py # Genera los .7z falsos (según AGENT_TIPO_FUENTES)
├── .env                     # Configuración LOCAL (no subir, §35)
├── .env.example             # Plantilla de configuración
└── requirements.txt         # Nota: solo stdlib, sin pip install
```

## ⚠️ Sincronización entre agente/ y agente_6_5/

`main.py`, `config.py`, `logger.py`, `api_client.py` y `scripts/simular_respaldos.py`
son **código común duplicado** a propósito (dos proyectos independientes en
máquinas distintas, sin pip para compartir paquetes). **Un fix en cualquiera de
esos cinco archivos debe aplicarse en los DOS proyectos** para no perder
sincronía.

La carpeta `checkers/` NO se comparte: cada proyecto trae SOLO los checkers de
sus propias fuentes, expuestos por `checkers/__init__.py` → `crear_checker()`
(despacha por `tipo_fuente` según lo que traiga cada proyecto). El filtro de
fuentes vive en `config.py` → `AGENT_TIPO_FUENTES`, así el código común es
idéntico y cada agente solo difiere en su `.env` y en sus `checkers/`:

| Proyecto | `AGENT_TIPO_FUENTES` | Checkers que trae | Bases que valida |
|---|---|---|---|
| `agente/` (10.0.3.8) | `SQL,MONGO` | `sql_backup.py`, `mongo_backup.py` | 44 SQL + 1 Mongo |
| `agente_6_5/` (192.168.6.5) | `MICROSIP,MERCALTOS` | `microsip_backup.py`, `mercaltos_backup.py` | 1 Microsip + 1 Mercaltos |

## Correr en local (simulación)

```bash
cd C:\proyectos\monitoreo-soporte\agente_6_5
copy .env.example .env        # completar AGENT_API_KEY (la del agente 192.168.6.5)
python scripts\simular_respaldos.py                # crea .7z falso en data\simulacion
python main.py                                     # valida y reporta al backend local
```

Opciones útiles (mismas que el agente 1):

```bash
python scripts\simular_respaldos.py --omitir MICROSIP_BACKUP_DIARIO          # → ERROR
python scripts\simular_respaldos.py --atrasado MICROSIP_BACKUP_DIARIO        # → ADVERTENCIA
python main.py --fecha 2026-08-15 --origen C:\temp\sim --dry-run             # sin reportar
python main.py --solo MICROSIP_BACKUP_DIARIO
```

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `API_BASE_URL` | Backend central en `192.168.6.2`. **Producción: siempre `https://…` (§38)** |
| `AGENT_API_KEY` | Key del agente `<AgenteId>.<secreto>` — la de **AGENTE_192.168.6.5** (su propia key, distinta del 10.0.3.8) |
| `AGENT_ORIGEN_DIR` | Override de carpeta origen. En 192.168.6.5 **vacío**: usa `D:\Respaldos_Microsip\Local` del catálogo |
| `AGENT_TIPO_FUENTES` | Fuentes que valida este agente (defecto vacío = todas). En 6.5: `MICROSIP,MERCALTOS` |
| `AGENT_FECHA` | Override de fecha operativa (pruebas) |
| `SQL_JOBS_SERVER` / `SQL_JOBS_USER` / `SQL_JOBS_PASSWORD` | Opcional; solo se llena si este agente también monitorea SQL Agent de alguna instancia |
| `HTTP_TIMEOUT` / `HTTP_RETRIES` / `HTTP_RETRY_DELAY` | Red y reintentos (§13) |
| `LOG_LEVEL` | `INFO` / `DEBUG` |

## Despliegue en 192.168.6.5 (Task Scheduler)

1. Copiar la carpeta `agente_6_5/` al servidor (sin `.env`, sin `data/`).
2. Crear `.env` con:
   ```
   API_BASE_URL=https://192.168.6.2
   AGENT_API_KEY=<AgenteId.secreto>
   AGENT_ORIGEN_DIR=            # vacío: toma D:\Respaldos_Microsip\Local del catálogo
   AGENT_TIPO_FUENTES=MICROSIP,MERCALTOS
   ```
3. Probar manualmente: `python main.py` (esperado: 1 base OK, exit 0).
4. Task Scheduler → Tarea diaria (después de la ventana nocturna §29):
   - Programa: `C:\Python311\python.exe`
   - Argumentos: `C:\monitoreo\agente_6_5\main.py`
   - Registrar **código de salida**: 0 = sin errores, 1 = hubo ERROR.
5. Verificar en el dashboard la ejecución de MICROSIP_BACKUP_DIARIO.

## Notas de diseño

- **El agente no decide incidencias ni elimina archivos**: solo valida y reporta (§26, §30).
- **Ventana simétrica** (a diferencia de SQL/Mongo): `HoraEsperada ± Tolerancia`
  = 19:00–01:00 para 22:00 ± 180. Un `.7z` a las 21:00 o a las 00:32 del día
  siguiente es válido (§10 Microsip).
- **`.7z` viejos ≠ respaldo de hoy**: solo cuenta el archivo dentro de la ventana;
  un `.7z` de otro día NO evita el ERROR de faltante.
- **Patrón estricto**: `Microsip_Backups_YYYYMMDD_HHMMSS.7z` (regex anclada) —
  archivos `.7z.tmp` a medio escribir o con otro formato no calzan.
- **Fuera de horario = ADVERTENCIA** (sin incidencia); **ERROR** (faltante/vacío)
  sí genera incidencia automática (§26).
- **Idempotencia**: reejecutar actualiza en lugar de duplicar (UNIQUE Base+Fecha, §35).
- **Reintentos**: fallas de red se reintentan (`HTTP_RETRIES`); los 4xx no.
- **TLS**: el header `X-Agent-Key` solo debe viajar por `https://` (§38).
