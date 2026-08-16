# Agente 10.0.3.8 — SQL + Mongo Backup Checker (Fase 4)

Agente **independiente** del backend (se ejecutará en el servidor 10.0.3.8 vía
Task Scheduler). Valida los respaldos SQL y el dump Mongo diario contra el
catálogo del sistema y reporta el resultado; el backend decide las incidencias
(§26). Microsip NO va aquí: lo valida el agente_6_5/.

**Solo biblioteca estándar de Python 3.11+** — no requiere `pip install` en el
servidor (urllib, json, logging, pathlib, datetime).

## ¿Qué hace?

```
1. Lee su configuración del backend  GET /api/v1/ingesta/configuracion (X-Agent-Key)
   → bases de SUS fuentes (SQL,MONGO), ruta origen, horarios por día (§35: nada quemado).
2. Para cada base valida la carpeta origen con su checker:
   - ¿existe el archivo de respaldo? (prefijo <NombreBase> + .bak, el más reciente)
   - ¿tamaño > 0?
   - ¿tipo correcto? (FULL / DIFERENCIAL según el nombre o el esperado)
   - ¿dentro de la ventana esperada? (HoraEsperada ± tolerancia, §29)
3. Reporta cada base          POST /api/v1/respaldos/ejecuciones (idempotente)
   - OK            -> archivo correcto y a tiempo
   - ADVERTENCIA   -> archivo presente pero fuera de horario, tipo distinto,
                      o fecha del NOMBRE distinta a la operativa
   - ERROR         -> sin archivo de HOY (aunque existan viejos) / vacío / carpeta no accesible
   - NO_APLICA     -> el día no aplica para la base
   El backend crea la incidencia automática (DetectadaPor=SISTEMA) si hay ERROR.
```

## Estructura

```
agente/
├── main.py                  # Orquesta: config → validar → reportar
├── config.py                # Variables de entorno + .env (sin dependencias)
├── logger.py                # Logging estructurado (§35)
├── api_client.py            # Cliente HTTP (urllib, reintentos §13, X-Agent-Key)
├── checkers/
│   ├── sql_backup.py        # SQL Backup Checker (§9)
│   └── mongo_backup.py      # Mongo Backup Checker (§9 Mongo)
├── scripts/
│   └── simular_respaldos.py # Genera archivos falsos (según AGENT_TIPO_FUENTES)
├── .env.example             # Plantilla de configuración
└── requirements.txt         # Nota: solo stdlib, sin pip install
```

## ⚠️ Sincronización con agente_6_5/

`main.py`, `config.py`, `logger.py`, `api_client.py` y `scripts/simular_respaldos.py`
son **código común duplicado** a propósito entre `agente/` (10.0.3.8) y
`agente_6_5/` (192.168.6.5): dos proyectos independientes en máquinas distintas,
sin pip para compartir paquetes. **Un fix en cualquiera de esos cinco archivos
debe aplicarse en los DOS proyectos.**

La carpeta `checkers/` NO se comparte: cada proyecto trae SOLO los checkers de
sus propias fuentes, expuestos por `checkers/__init__.py` → `crear_checker()`
(este despacha por `tipo_fuente` según lo que traiga cada proyecto). El filtro
de fuentes vive en `config.py` → `AGENT_TIPO_FUENTES`, así el código común es
idéntico y cada agente solo difiere en su `.env` y en sus `checkers/`:

| Proyecto | `AGENT_TIPO_FUENTES` | Checkers que trae | Bases que valida |
|---|---|---|---|
| `agente/` (10.0.3.8) | `SQL,MONGO` | `sql_backup.py`, `mongo_backup.py` | 44 SQL + 1 Mongo |
| `agente_6_5/` (192.168.6.5) | `MICROSIP,MERCALTOS` | `microsip_backup.py`, `mercaltos_backup.py` | 1 Microsip + 1 Mercaltos |

## Correr en local (simulación)

```bash
cd C:\proyectos\monitoreo-soporte\agente
copy .env.example .env        # completar AGENT_API_KEY (y AGENT_ORIGEN_DIR con tu carpeta de prueba)
python scripts\simular_respaldos.py                # crea .bak falsos en data\simulacion
python main.py                                     # valida y reporta al backend local
```

Opciones útiles del simulador (para probar los estados):

```bash
python scripts\simular_respaldos.py --omitir DWCalzamoda            # → ERROR (faltante)
python scripts\simular_respaldos.py --atrasado PROSUR_PRIME_BLINK   # → ADVERTENCIA (fuera de ventana)
python scripts\simular_respaldos.py --fecha 2026-08-11 --dir C:\temp\sim
```

Opciones del agente:

```bash
python main.py --fecha 2026-08-11     # fecha operativa explícita
python main.py --origen C:\temp\sim   # override de carpeta (por si no usas AGENT_ORIGEN_DIR)
python main.py --solo PROSUR_PRIME    # una sola base
python main.py --dry-run              # valida sin reportar
```

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `API_BASE_URL` | Backend. **Producción: siempre `https://…` (§38)** |
| `AGENT_API_KEY` | Key del agente `<AgenteId>.<secreto>` (de `POST /api/v1/agentes`) |
| `AGENT_ORIGEN_DIR` | Override de carpeta origen. En 10.0.3.8 **vacío**: usa la ruta del catálogo (`G:\TempRespSQLServer`) |
| `AGENT_TIPO_FUENTES` | Fuentes que valida este agente (defecto vacío = todas). En 10.0.3.8: `SQL,MONGO` |
| `AGENT_FECHA` | Override de fecha operativa (pruebas) |
| `AGENT_MATCH_SUFIJOS` | Sufijos de archivo considerados respaldos (defecto `.bak,.BAK`) |
| `HTTP_TIMEOUT` / `HTTP_RETRIES` / `HTTP_RETRY_DELAY` | Red y reintentos (§13) |
| `LOG_LEVEL` | `INFO` / `DEBUG` |

## Despliegue en 10.0.3.8 (Task Scheduler)

1. Copiar la carpeta `agente/` al servidor (sin `.env`, sin `data/`).
2. Crear `.env` con:
   ```
   API_BASE_URL=https://<host-del-backend>
   AGENT_API_KEY=<AgenteId.secreto>
   AGENT_ORIGEN_DIR=            # vacío: toma G:\TempRespSQLServer del catálogo
   ```
3. Probar manualmente: `python main.py` (esperado: 4 bases OK, exit 0).
4. Task Scheduler → Tarea diaria ~08:30 (después de la ventana nocturna §29):
   - Programa: `C:\Python311\python.exe`
   - Argumentos: `C:\monitoreo\agente\main.py`
   - Registrar **código de salida**: 0 = sin errores, 1 = hubo ERROR (visible en el resultado de la tarea).
5. Verificar en el dashboard: respaldos 4/4 y, si algo falló, la incidencia abierta.

## Notas de diseño

- **El agente no decide incidencias ni elimina archivos**: solo valida y reporta
  (§26, §30 — la transferencia/eliminación son fases posteriores).
- **Archivos viejos ≠ respaldo de hoy**: solo cuenta el archivo dentro de la ventana
  esperada (cubre medianoche); un archivo de otro día NO evita el ERROR de faltante.
- **Comparación nombre/fecha/tamaño (§9)**: tamaño > 0, mtime dentro de la ventana,
  tipo según el marcador del archivo (`_FULL`/`_DIF`) y, si el nombre trae fecha
  (`YYYYMMDD`), debe coincidir con la fecha operativa — si no, ADVERTENCIA.
- **Colisiones de prefijo resueltas**: `PROSUR_PRIME` no captura archivos de
  `PROSUR_PRIME_DATA`/`_BLINK` — se rechazan los archivos que también matchean
  una base de nombre más largo (longest-prefix).
- **Sufijo de respaldo obligatorio**: los artefactos `.bak.tmp` o sin extensión se
  ignoran (§30: copia incompleta).
- **Nombrado tolerante**: cualquier formato tras el nombre de la base (fecha ISO
  `DWCalzamoda_2026-08-09.bak`, `_manual`, etc.) se acepta — la fecha real se
  valida con el mtime y con la fecha del nombre cuando el archivo la trae.
- **Fuera de horario = ADVERTENCIA** (sin incidencia): el respaldo existe, solo fue
  tardío; la bitácora lo muestra y Soporte decide. Los ERROR (faltante/vacío) sí
  generan incidencia automática (§26).
- **Idempotencia**: reejecutar el agente actualiza en lugar de duplicar
  (UNIQUE Base+Fecha en el backend, §35).
- **Reintentos**: fallas de red se reintentan (`HTTP_RETRIES`); los errores 4xx
  no se reintentan (ej. key inválida).
- **TLS**: el header `X-Agent-Key` solo debe viajar por `https://` (§38). El
  backend en producción no arranca sin certificados.
