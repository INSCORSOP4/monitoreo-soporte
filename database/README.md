# MONITOREO_SOPORTE — Modelo de datos (Fase 2)

Esquema de la base de datos del **Sistema de Monitoreo y Bitácora de Soporte** (Plan Maestro, sección 7 y 23). Traduce las secciones 2 (infraestructura), 9/10 (validación SQL por base) y 27 (historial) del plan a un esquema real.

## Cómo ejecutar

```sql
-- Desde SSMS / sqlcmd:
:r MONITOREO_SOPORTE.sql
```

Requiere SQL Server 2019 (producción en `10.0.3.8`). El script es idempotente (`IF OBJECT_ID... IS NULL`), puede ejecutarse varias veces.

## Diagrama entidad-relación

```
┌────────────────────┐      ┌─────────────────────┐
│ cat_roles          │      │ cat_servidores      │
│────────────────────│      │─────────────────────│
│ RolId PK           │◄─────│ ServidorId PK       │
│ Codigo             │      │ Nombre (10.0.3.8...)│
└────────────────────┘      │ Tipo (AWS/LOCAL/NAS)│
                            └──────────┬──────────┘
┌────────────────────┐                 │
│ cat_agentes (§8)   │                 │
│────────────────────│   Máquinas, NO personas:
│ AgenteId PK        │   AGENTE_10.0.3.8, etc.
│ Nombre UNIQUE      │   ApiKeyHash = bcrypt,
│ ApiKeyHash         │   la key en claro se
│ ServidorId FK ─────┼──► cat_servidores  (Disco Checker §33)
│ Activo             │   muestra UNA sola vez.
└────────────────────┘
┌────────────────────┐                 │
│ cat_usuarios       │                 │
│────────────────────│                 │
│ UsuarioId PK       │                 │
│ UsuarioExternoId ──┼──► SEGURIDAD_PROSUR (sin contraseñas)
│ RolId FK           │                 │
└─────────┬──────────┘                 │
          │                            │
┌─────────▼──────────┐   ┌─────────────▼──────────────┐
│ rotacion           │   │ cat_grupos_respaldo        │
│────────────────────│   │────────────────────────────│
│ UsuarioId FK       │   │ GrupoRespaldoId PK         │
│ Orden              │   │ Codigo (SQL_RESTO/FORTIA...)│
└────────────────────┘   └─────────────┬──────────────┘
                                       │
                ┌──────────────────────┴───────────────────────┐
                │                                               │
┌───────────────▼──────────────┐        ┌───────────────────────▼──────┐
│ cat_bases_datos              │        │ reglas_retencion             │
│──────────────────────────────│        │──────────────────────────────│
│ BaseDatosId PK               │        │ GrupoRespaldoId FK (UNIQUE)  │
│ GrupoRespaldoId FK           │        │ MesesRetencion = 3           │
│ ServidorOrigenId FK          │        │ Conservar 1 Full + 1 Dif/mes │
│ NombreBase (41 RESTO, 3 F.)  │        └──────────────────────────────┘
│ TipoFuente (SQL/MONGO/...)   │
└──────────┬───────────────────┘
           │ 1:1
┌──────────▼───────────────────┐     ┌────────────────────────────────┐
│ rutas_origen_destino         │     │ horarios_esperados             │
│──────────────────────────────│     │────────────────────────────────│
│ BaseDatosId FK (UNIQUE)      │     │ BaseDatosId FK                 │
│ RutaOrigen (G:\Temp...)      │     │ DiaSemana (1=Lun..7=Dom)       │
│ RutaDestino (\\NAS\...)      │     │ DiaAplica (Mercaltos: dom=0)   │
│ ServidorDestinoId FK (NAS)   │     │ TipoBackupEsperado FULL/DIF    │
│ EliminarOrigenTrasTransfer.  │     │ HoraEsperada 22:00             │
└──────────────────────────────┘     │ ToleranciaMinutos (ventana §29)│
                                      └────────────────────────────────┘
┌──────────────────────────────┐     ┌────────────────────────────────┐
│ respaldos_ejecuciones        │◄────│ cat_tipos_incidencia           │
│──────────────────────────────│     └──────────────┬─────────────────┘
│ BaseDatosId FK               │                    │
│ FechaEjecucion               │     ┌──────────────▼─────────────────┐
│ Estado OK/ERROR/...          │     │ incidencias                    │
│ UNIQUE(Base,Fecha) idempot.  │     │────────────────────────────────│
└──────────┬───────────────────┘     │ TipoIncidenciaId FK            │
           │                         │ ServidorId FK / BaseDatosId FK │
           │ 1:N                     │ Estado (ABIERTA/EN_PROCESO/...)│
┌──────────▼───────────────────┐     │ ResponsableDiaId FK (§21)      │
│ transferencias               │     │ UsuarioAtendioId FK            │
│──────────────────────────────│     └──────────┬─────────────────────┘
│ EjecucionId FK               │                │ 1:N
│ Estado (COMPLETADA/FALLIDA)  │     ┌──────────▼─────────────────────┐
│ OrigenEliminado (§30: solo   │     │ acciones_incidencia            │
│   se elimina si COMPLETADA)  │     │────────────────────────────────│
│ HashOrigen/HashDestino (§12) │     │ IncidenciaId FK / UsuarioId FK │
└──────────────────────────────┘     │ Descripcion / Resultado        │
                                      └────────────────────────────────┘
┌──────────────────────────────┐     ┌────────────────────────────────┐
│ alertas                      │     │ responsables_dia               │
│──────────────────────────────│     │────────────────────────────────│
│ IncidenciaId/Ejecucion/Lectu │     │ Fecha (UNIQUE)                 │
│ TipoEvento / Estado / Fecha  │     │ UsuarioId FK (responsable día) │
│ (dedupe por entidad §28)     │     │ OrigenAsignacion AUTO/MANUAL   │
└──────────────────────────────┘     └────────────────────────────────┘
                                      └────────────────────────────────┘
┌──────────────────────────────┐
│ historial (§27, §35)         │  Auditoría genérica:
│──────────────────────────────│  Entidad + EntidadId + TipoEvento
│ UsuarioId FK / Entidad /     │  + DatosAntes/Despues (JSON)
│ TipoEvento / JSON            │
└──────────────────────────────┘
┌──────────────────────────────┐
│ discos_lecturas (§33)        │  Disco Checker (agente): espacio por
│──────────────────────────────│  servidor y unidad, una lectura/día
│ ServidorId FK / UnidadLetra  │  UNIQUE(Servidor,Unidad,Fecha)
│ FechaLectura / EspacioTotal  │  = misma idempotencia que
│ LibreGB / PorcentajeLibre    │  respaldos_ejecuciones
│ Estado OK/ADVERTENCIA/ERROR  │
└──────────────────────────────┘
```

## Decisiones de diseño

| Decisión | Detalle |
|---|---|
| **Usuarios locales con hash bcrypt** | `cat_usuarios` guarda `PasswordHash` (bcrypt, nunca en claro) y `DebeCambiarPassword=1` para forzar el cambio en el primer login. `UsuarioExternoId` es opcional (índice único filtrado): permite usuarios creados localmente y sigue evitando duplicados cuando la referencia a `SEGURIDAD_PROSUR` sí existe. |
| **Nota de equipo — índices únicos filtrados con columna NULL** | En SQL Server `NULL = NULL` dentro de un índice único: cualquier columna nullable que participe en un índice único filtrado necesita predicado explícito. Ej. 1: `UQ_cat_usuarios_UsuarioExternoId` (`WHERE UsuarioExternoId IS NOT NULL`). Ej. 2 (bug real): los índices SISTEMA de incidencias no excluían `BaseDatosId IS NULL`, y dos incidencias de disco de servidores distintos (BaseDatosId=NULL) colisionaban (Msg 2601) — se corrigió con `AND BaseDatosId IS NOT NULL`, dejando el caso disco a `UQ_incidencias_DISCO_*` (por ServidorId). **Regla**: al crear un índice único filtrado, revisar cada columna nullable del predicado y decidir explícitamente si se incluye (`IS NOT NULL`) o se excluye (`IS NULL`). |
| **Validación por base** (§9/§10) | `cat_bases_datos` registra cada una de las 44+3 bases (41 RESTO + 1 MONGO + 1 MICROSIP + 1 MERCALTOS + 3 FORTIA) con su grupo, servidor origen y tipo predeterminado. |
| **Horarios por día** (§9/§29) | `horarios_esperados` tiene una fila por `(Base, DiaSemana)`. Así "Lun-Sáb DIF / Dom FULL" y "Dom-Vie DIF / Sáb FULL" son datos, no lógica en código (§35). |
| **Rutas estrictas** (§5) | Solo se tocan las rutas registradas en `rutas_origen_destino`. El NAS tiene carpetas personales; el sistema nunca opera fuera de estas rutas. |
| **Idempotencia** (§35) | `UNIQUE (BaseDatosId, FechaEjecucion)` en ejecuciones: reejecutar un agente no duplica. |
| **Ejecuciones de pasos SQL Agent** | `jobs_pasos_ejecuciones` conserva el estado, hora y mensaje real de SQL Server por paso y día. `UNIQUE (PasoMonitoreadoId, FechaEjecucion)` evita duplicados y `IncidenciaId` vincula errores con Soporte. |
| **Incidencias de SQL Agent** | `JOB_SQL_AGENT` clasifica por separado los errores detectados en jobs y pasos de SQL Server Agent. |
| **Regla crítica de eliminación** (§30) | `transferencias.OrigenEliminado` solo puede ponerse en 1 cuando `Estado = 'COMPLETADA'` (regla validada por la capa de aplicación/agente). Nunca `copiar -> eliminar`. |
| **Responsable ≠ Interventor** (§21) | `incidencias.ResponsableDiaId` (quién es responsable ese día) y `incidencias.UsuarioAtendioId` + `acciones_incidencia.UsuarioId` (quién intervino) son campos distintos, como pide el plan. |
| **Historial auditable** (§27) | Tabla genérica `historial` con JSON antes/después permite responder "¿quién intervino?", "¿cuánto tardó?", "¿qué cambió en la rotación?". |
| **Anti-spam de alertas** (§28) | Las ADVERTENCIAS no crean incidencia (por diseño), así que la alerta NO se deduplica solo por `IncidenciaId`: se deduplica por la **entidad que la originó** — ERROR→`IncidenciaId`, ADVERTENCIA de respaldo→`EjecucionId`, ADVERTENCIA de disco→`LecturaDiscoId` — con índice único filtrado por cada combinación (predicado explícito sobre la columna nullable, nota de equipo). Solo `ENVIADA`/`SUPRIMIDA` suprimen; `FALLIDA`/`PENDIENTE` se reintentan sobre la misma fila. |
| **Retención configurable** (§31) | `reglas_retencion` por grupo: 3 meses, 1 Full + 1 Diferencial por mes. `DepuracionActiva` habilita la depuración en fase posterior. |

## Pendientes de fases posteriores (no bloquean este esquema)

- Rotación/regeneración de API key de agentes (hoy: crear y borrar/recrear).

- `data/seed_bases_res_to.sql` — ya no es necesario: las 40 bases RESTO, sus rutas (`rutas_origen_destino`) y horarios (`horarios_esperados`) se cargan en el script principal, sección 6.8.
- Catálogos de Jobs, Archivos de confianza y Actividades manuales (Fases 7–8).
- Triggers de auditoría (hoy el historial se registra desde la API).
