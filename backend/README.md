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
    │   ├── security.py        #   Emisión/validación de tokens JWT
    │   └── logging.py         #   Logging estructurado (§35 observabilidad)
    ├── models/                # ORM — espejo exacto del esquema SQL
    │   ├── catalogos.py       #   cat_roles, cat_usuarios, cat_servidores, grupos, bases
    │   ├── configuracion.py   #   rutas, horarios, retención
    │   ├── operacion.py       #   ejecuciones, transferencias, incidencias, alertas, rotación
    │   └── historial.py       #   historial (§27)
    ├── schemas/               # Schemas Pydantic (request/response)
    ├── services/              # Lógica de negocio
    │   └── auth_service.py    #   Autenticación: stub dev / usuarios locales bcrypt
    └── api/
        ├── deps.py            # get_db, get_current_user (JWT)
        └── v1/                # Routers por módulo (§32 Fase 3)
            ├── router.py      #   Agregador /api/v1
            ├── auth.py        #   POST /auth/login
            ├── usuarios.py    #   CRUD cat_usuarios
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
| GET | `/api/v1/servidores` | Catálogo de servidores |
| GET | `/api/v1/bases-datos?grupo_respaldo_id=N` | Catálogo de bases (§9/§10) |
| GET | `/api/v1/respaldos/resumen?fecha=2026-08-08` | Resumen por grupo (bitácora §24) |
| GET | `/api/v1/dashboard/resumen?fecha=2026-08-08` | Indicadores del dashboard (§25) |
| GET | `/api/v1/incidencias?estado=ABIERTA` | Incidencias abiertas (§26) |
| GET | `/api/v1/historial?entidad=incidencias` | Historial de auditoría (§27) |

## Autenticación (§22)

- `AUTH_MODE=stub` (desarrollo): usuario `admin` / password `admin` — **nunca en producción**.
- `AUTH_MODE=seguridad`: valida contra `MONITOREO_SOPORTE.dbo.cat_usuarios` (usuarios locales creados con `POST /usuarios`; contraseña almacenada como hash bcrypt, `DebeCambiarPassword` fuerza el cambio en el primer login).
- `UsuarioExternoId` es opcional: referencia lógica a `SEGURIDAD_PROSUR` cuando exista vínculo; los usuarios pueden crearse localmente.
- Los endpoints protegidos requieren `Authorization: Bearer <token>`.

## Pendientes de la Fase 3

- Resolver el rol del usuario desde `cat_roles` en el login (hoy se devuelve SOPORTE por defecto).
- Definir columna de login/usuario (hoy se autentica por `nombre_completo`).
- Módulos de Jobs, Archivos de confianza, Actividades manuales y Configuración (fases 7-8 del plan).
- Endpoint de ingesta para agentes (reporte de ejecuciones/transferencias).
