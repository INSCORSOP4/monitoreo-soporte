# MONITOREO_SOPORTE — Backend (Fase 3)

API FastAPI del **Sistema de Monitoreo y Bitácora de Soporte**, construida desde cero sobre la base `MONITOREO_SOPORTE` (ver `../database/`).

## Requisitos

- Python 3.11+
- ODBC Driver para SQL Server instalado (17 o 18): `DB_DRIVER` en `.env`
- Acceso a `MONITOREO_SOPORTE` (SQL Server 2019)

## Puesta en marcha

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows
pip install -r requirements.txt

copy .env.example .env            # completar credenciales (NUNCA subir .env real)
python run.py
```

Documentación interactiva: http://localhost:8000/docs — Health check: http://localhost:8000/api/v1/health

## Estructura por módulos (§32 Fase 3)

```
backend/
├── run.py                     # Punto de entrada uvicorn
├── .env.example               # Plantilla de configuración (§35: sin credenciales en código)
├── requirements.txt
└── app/
    ├── main.py                # Aplicación FastAPI (CORS, routers)
    ├── core/                  # Infraestructura
    │   ├── config.py          #   Configuración vía pydantic-settings (.env)
    │   ├── database.py        #   SQLAlchemy + pyodbc (pool_pre_ping para VPN, §6)
    │   ├── security.py        #   JWT + hashing bcrypt (contraseñas y API keys)
    │   └── logging.py         #   Logging estructurado (§35 observabilidad)
    ├── models/                # ORM — espejo exacto del esquema SQL
    │   ├── catalogos.py       #   cat_roles, cat_usuarios, cat_servidores, grupos, bases
    │   ├── configuracion.py   #   rutas, horarios, retención
    │   ├── operacion.py       #   ejecuciones, transferencias, incidencias, alertas, rotación
    │   └── historial.py       #   historial (§27)
    ├── schemas/               # Schemas Pydantic (request/response)
    ├── services/              # Lógica de negocio
    │   ├── auth_service.py    #   Autenticación: stub dev / usuarios locales bcrypt
    │   └── incidencias_service.py  #   Incidencias automáticas SISTEMA (§26)
    └── api/
        ├── deps.py            # get_db, get_current_user (JWT humanos)
        ├── deps_agent.py      # verify_agent_key (X-Agent-Key, §8)
        └── v1/                # Routers por módulo (§32 Fase 3)
            ├── router.py      #   Agregador /api/v1
            ├── auth.py        #   POST /auth/login
            ├── usuarios.py    #   CRUD cat_usuarios
            ├── roles.py       #   Catálogo de roles
            ├── agentes.py     #   Agentes (máquinas) con API key (§8)
            ├── ingesta.py     #   Ingesta de agentes (X-Agent-Key, §8)
            ├── servidores.py  #   CRUD cat_servidores
            ├── bases_datos.py #   CRUD cat_bases_datos (§9, §10)
            ├── respaldos.py   #   Bitácora diaria y resumen por grupo (§24)
            ├── incidencias.py #   Incidencias + acciones (§26)
            ├── alertas.py     #   Bitácora de alertas (§28)
            ├── historial.py   #   Consultas de auditoría (§27)
            ├── dashboard.py   #   Resumen general (§25)
            └── health.py      #   Estado de API y BD
```

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/auth/login` | Autenticación (JWT) |
| POST | `/api/v1/agentes` | Crea agente y devuelve su API key (única vez, formato `<AgenteId>.<secreto>`) |
| GET | `/api/v1/agentes` | Lista agentes (sin exponer el hash) |
| GET | `/api/v1/ingesta/agente` | Identidad del agente (header `X-Agent-Key`, §8) |
| GET | `/api/v1/ingesta/configuracion` | Catálogo completo para el agente: bases + rutas + horarios (§35, Fase 4) |
| GET | `/api/v1/servidores` | Catálogo de servidores |
| GET | `/api/v1/bases-datos?grupo_respaldo_id=N` | Catálogo de bases (§9/§10) |
| POST | `/api/v1/respaldos/ejecuciones` | Ingesta del agente (§8): reporta validación diaria por base (idempotente por Base+Fecha). Si `estado=ERROR`, crea/reutiliza la incidencia automática `SISTEMA` con el responsable del día (§26) |
| POST | `/api/v1/jobs/ejecuciones` | Ingesta de pasos de SQL Agent: idempotente por Paso+Fecha; un `ERROR` crea/reutiliza incidencia `JOB_SQL_AGENT` |
| GET | `/api/v1/respaldos/resumen?fecha=2026-08-08` | Resumen por grupo (bitácora §24) |
| GET | `/api/v1/dashboard/resumen?fecha=2026-08-08` | Indicadores del dashboard (§25) |
| GET | `/api/v1/responsables-dia/hoy` | Responsable del día para el dashboard (§21): dispara la asignación automática por rotación si aún no existe (solo días hábiles) |
| PUT | `/api/v1/responsables-dia/{fecha}` | Asignación MANUAL del responsable (solo COORDINADOR/ADMINISTRADOR, §21): fija UsuarioId con `OrigenAsignacion='MANUAL'` y registra `UsuarioReasignoId`. Una vez MANUAL, la lógica automática nunca lo sobrescribe |
| GET | `/api/v1/incidencias?estado=ABIERTA` | Incidencias abiertas (§26) |
| GET | `/api/v1/alertas` | Bitácora de envíos de correo (§28): dedupe por entidad, estados ENVIADA/FALLIDA/PENDIENTE/SUPRIMIDA |
| GET | `/api/v1/historial?entidad=incidencias` | Historial de auditoría (§27) |

## Autenticación (§22)

- `AUTH_MODE=stub` (desarrollo): correo `admin` / password `admin` — **nunca en producción**.
- `AUTH_MODE=seguridad`: valida contra `MONITOREO_SOPORTE.dbo.cat_usuarios` (usuarios locales creados con `POST /usuarios`; contraseña almacenada como hash bcrypt, `DebeCambiarPassword` fuerza el cambio en el primer login).
- **Agentes (§8)**: los endpoints de ingesta usan `verify_agent_key` con header `X-Agent-Key`. Formato `<AgenteId>.<secreto>`: el middleware separa el `AgenteId`, hace **UN SOLO lookup por PK** y **UN SOLO bcrypt** contra `ApiKeyHash` (hash del secreto, `Activo=1`). No usan JWT humano.
- **TLS obligatorio para agentes (§38)**: la `X-Agent-Key` viaja en el header; la VPN cifra entre redes pero NO dentro de la red. En producción los agentes deben llamar siempre a `https://…` — el backend sirve TLS si `SSL_CERTFILE`/`SSL_KEYFILE` están definidos en `.env` (ver `.env.example`).
- El **correo es el identificador de login** (único y obligatorio: `UQ_cat_usuarios_Correo`); el login busca `WHERE Correo = ?`.
- `UsuarioExternoId` es opcional: referencia lógica a `SEGURIDAD_PROSUR` cuando exista vínculo; los usuarios pueden crearse localmente.
- Los endpoints protegidos requieren `Authorization: Bearer <token>`.

## Incidencias automáticas (§26)

La ingesta del agente solo reporta hechos; las incidencias las genera el backend:

- `POST /respaldos/ejecuciones` con `estado=ERROR` → crea la incidencia con `DetectadaPor='SISTEMA'`, tipo según el grupo de la base (`RESPALDO_SQL/MONGO/MICROSIP/MERCALTOS`) y `ResponsableDiaId` = responsable del día vigente (`responsables_dia`, §21).
- Idempotente: reenvíos del mismo ERROR reutilizan la incidencia abierta de (base, fecha); si el estado vuelve a `OK`, la incidencia **no** se cierra automáticamente — la cierra Soporte al registrar la intervención (§26).
- Si no hay responsable para la fecha, se asigna automáticamente por **rotación** (`rotacion`, §21): se toma el último `OrigenAsignacion='AUTO'` anterior a la fecha, se avanza al siguiente `Orden` activo (salta `Suspendido=1` y usuarios `Activo=0`, da la vuelta al final) y se registra la fila AUTO. Sin asignación previa se empieza en `Orden=1`. Si no hay participantes activos, la incidencia se crea con `ResponsableDiaId NULL` (queda para la revisión) y se registra un warning.
- La asignación automática es **lazy y solo en días hábiles**: en fin de semana (sáb/dom) no se intenta la rotación — la incidencia queda con `ResponsableDiaId NULL` y el log registra el aviso; el responsable se calcula bajo demanda (al primer ERROR del día) y se guarda con `OrigenAsignacion='AUTO'` antes de usarse.

## Alertas por correo (§28)

Los endpoints de ingesta (`POST /respaldos/ejecuciones` y `POST /discos/lecturas`) crean alertas para **todo Soporte** en `ERROR` y `ADVERTENCIA` (no-op en OK). FastAPI ejecuta el SMTP con `BackgroundTasks` después de responder al agente, por lo que un servidor de correo lento o caído no bloquea la ingesta. La bitácora queda en `alertas` (`GET /api/v1/alertas`, JWT humano).

**Configuración (`.env`, nunca en el chat ni en el repo):** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (+ `SMTP_TLS`, `SMTP_TIMEOUT`, `ALERTA_ROL_DESTINATARIOS`). Cualquier fallo de configuración, red, TLS o autenticación marca la alerta `FALLIDA` y guarda `ErrorDetalle`.

**Anti-spam — dedupe por ENTIDAD, no solo por IncidenciaId:** las ADVERTENCIAS no crean incidencia (por diseño), así que la alerta se deduplica por la entidad que la originó (barrera BD: índices únicos filtrados en `alertas`):

| Evento | Clave de dedupe |
|---|---|
| ERROR de respaldo | `IncidenciaId` (incidencia SISTEMA §26) |
| ADVERTENCIA de respaldo | `EjecucionId` (idempotente por base+fecha) |
| ERROR de disco | `IncidenciaId` (DISCO_SERVIDOR) |
| ADVERTENCIA de disco | `LecturaDiscoId` (idempotente por servidor+unidad+fecha) |

Las alertas `FALLIDA` se reintentan con `POST /api/v1/alertas/{alerta_id}/reintentar`; el endpoint responde `202` y vuelve a ejecutar el SMTP en segundo plano sobre la **misma fila**.

## TLS / HTTPS (§38)

La VPN cifra el tráfico **entre redes**, pero dentro de la red la `X-Agent-Key` viaja en claro si el servicio usa HTTP plano. En producción:

1. Definir `SSL_CERTFILE` y `SSL_KEYFILE` en `.env` (certificado del servidor 10.0.3.8).
2. `python run.py` sirve HTTPS con esos archivos (`ssl_certfile`/`ssl_keyfile` de uvicorn).
3. Los agentes configuran su `BASE_URL` con `https://…` — nunca `http://`.

En desarrollo (loopback / VPN de confianza) pueden dejarse vacíos.

## Pendientes de la Fase 3

- Reporte de transferencias del agente (transferencias → NAS) y reporte de Jobs/Archivos (fases 6-7).
- Agente 10.0.3.8: proyecto independiente en `../agente/` (SQL Backup Checker, Fase 4).
- Módulos de Jobs, Archivos de confianza, Actividades manuales y Configuración (fases 7-8 del plan).
- Endpoint de rotación de API key (`POST /agentes/{id}/rotar-key`); hoy se rota vía `scripts/rotar_api_key_agente.py`.
