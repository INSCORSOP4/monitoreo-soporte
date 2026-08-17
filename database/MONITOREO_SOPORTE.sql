/* ============================================================================
   MONITOREO_SOPORTE — Esquema de base de datos v0.1
   ----------------------------------------------------------------------------
   Proyecto: Sistema de Monitoreo y Bitácora de Soporte (Plan Maestro §7, §23)
   Fase:     2 — Base de datos (orden de desarrollo, paso 1)

   Traduce al esquema las secciones del plan:
     §2  Infraestructura actual (servidores y fuentes de respaldo)
     §9  Validación SQL (41 bases RESTO, validación individual por base)
     §10 Validación SQL FORTIA (3 bases)
     §21 Asignación automática del responsable del día
     §22 Usuarios y roles (usuarios locales con hash bcrypt; UsuarioExternoId opcional)
     §23 Entidades principales de la base
     §26 Incidencias
     §27 Historial
     §28 Alertas
     §30 Regla crítica de eliminación (nunca copiar->eliminar)
     §31 Retención / depuración del NAS

   Convenciones:
     - Catálogos con prefijo cat_.
     - Tablas operativas sin prefijo.
     - Llaves primarias: <Tabla>Id INT IDENTITY.
     - Llaves foráneas: <EntidadRelacionada>Id (ej. ServidorId, BaseDatosId).
     - Fechas en DATETIME2, fechas de operación en DATE.
     - Estados con CHECK + valores en mayúsculas (OK, ERROR, ADVERTENCIA...).
     - Los catálogos de negocio son configurables desde BD (§35: nada quemado en código).

   Nota de alcance (Fase 2):
     - Este script crea las TABLAS NÚCLEO del modelo (secciones 2, 9, 10, 27).
     - Las entidades de fases posteriores (Jobs, Archivos de confianza,
       Actividades manuales, Depuración NAS) se agregarán en scripts de fase
       sin romper este esquema.
     - El catálogo de las 41 bases RESTO se carga en un script de seed aparte
       (data/seed_bases_res_to.sql) una vez confirmado el inventario exacto.

   Nota: los índices filtrados (incidencias SISTEMA/DISCO, alertas §28) requieren
   QUOTED_IDENTIFIER ON — declarado aquí para que el script corra en cualquier cliente.
============================================================================ */

SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================================
-- 0. CREACIÓN DE LA BASE
-- ============================================================================

IF DB_ID(N'MONITOREO_SOPORTE') IS NULL
BEGIN
    CREATE DATABASE MONITOREO_SOPORTE;
END
GO

USE MONITOREO_SOPORTE;
GO

-- ============================================================================
-- 1. CATÁLOGOS
-- ============================================================================

/* ----------------------------------------------------------------------------
   1.1 cat_roles  (§22) — Roles conceptuales del sistema
        Coordinador | Soporte | Administrador
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_roles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_roles
    (
        RolId            INT           NOT NULL IDENTITY(1,1),
        Codigo           VARCHAR(20)   NOT NULL,          -- COORDINADOR / SOPORTE / ADMINISTRADOR
        Nombre           VARCHAR(60)   NOT NULL,
        Descripcion      VARCHAR(255)  NULL,
        Activo           BIT           NOT NULL CONSTRAINT DF_cat_roles_Activo DEFAULT (1),
        FechaRegistro    DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_roles_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_roles PRIMARY KEY CLUSTERED (RolId),
        CONSTRAINT UQ_cat_roles_Codigo UNIQUE (Codigo)
    );
END
GO

/* ----------------------------------------------------------------------------
   1.2 cat_usuarios  — Usuarios del sistema (creados localmente en MONITOREO_SOPORTE)
        - La contraseña se almacena SOLO como hash bcrypt (PasswordHash), nunca en claro.
        - DebeCambiarPassword=1 obliga a cambiar la contraseña en el primer login.
        - UsuarioExternoId es OPCIONAL: referencia lógica a SEGURIDAD_PROSUR.dbo.cat_usuarios
          cuando exista un vínculo; permite NULL para usuarios creados localmente.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_usuarios', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_usuarios
    (
        UsuarioId            INT           NOT NULL IDENTITY(1,1),
        UsuarioExternoId     INT           NULL,          -- FK lógica a SEGURIDAD_PROSUR (opcional)
        NombreCompleto       VARCHAR(120)  NOT NULL,
        Correo               VARCHAR(120)  NOT NULL,      -- identificador real de login: único y obligatorio
        RolId                INT           NOT NULL,
        Activo               BIT           NOT NULL CONSTRAINT DF_cat_usuarios_Activo DEFAULT (1),
        PasswordHash         VARCHAR(255)  NULL,          -- hash bcrypt (nunca contraseña en claro)
        DebeCambiarPassword  BIT           NOT NULL CONSTRAINT DF_cat_usuarios_DebeCambiar DEFAULT (1),
        FechaRegistro        DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_usuarios_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_usuarios PRIMARY KEY CLUSTERED (UsuarioId),
        CONSTRAINT UQ_cat_usuarios_Correo UNIQUE (Correo),
        CONSTRAINT FK_cat_usuarios_Rol FOREIGN KEY (RolId) REFERENCES dbo.cat_roles (RolId)
    );
END
GO

-- Índice único FILTRADO: permite múltiples usuarios con UsuarioExternoId NULL
-- (usuarios locales), pero evita duplicados cuando el campo sí existe.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_cat_usuarios_UsuarioExternoId' AND object_id = OBJECT_ID(N'dbo.cat_usuarios')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_cat_usuarios_UsuarioExternoId
        ON dbo.cat_usuarios (UsuarioExternoId)
        WHERE UsuarioExternoId IS NOT NULL;
GO

/* ----------------------------------------------------------------------------
   1.3 cat_servidores  (§2, §4) — Servidores monitoreados y el NAS
        Tipos: AWS / LOCAL / NAS
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_servidores', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_servidores
    (
        ServidorId       INT           NOT NULL IDENTITY(1,1),
        Nombre           VARCHAR(50)   NOT NULL,          -- 10.0.3.8 / 192.168.6.5 / 192.168.6.9
        Descripcion      VARCHAR(255)  NULL,
        TipoServidor     VARCHAR(20)   NOT NULL,          -- AWS / LOCAL / NAS
        EsNAS            BIT           NOT NULL CONSTRAINT DF_cat_servidores_EsNAS DEFAULT (0),
        EsOrigenRespaldo BIT           NOT NULL CONSTRAINT DF_cat_servidores_EsOrigen DEFAULT (0),
        Activo           BIT           NOT NULL CONSTRAINT DF_cat_servidores_Activo DEFAULT (1),
        FechaRegistro    DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_servidores_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_servidores PRIMARY KEY CLUSTERED (ServidorId),
        CONSTRAINT UQ_cat_servidores_Nombre UNIQUE (Nombre),
        CONSTRAINT CK_cat_servidores_Tipo CHECK (TipoServidor IN ('AWS', 'LOCAL', 'NAS'))
    );
END
GO

/* ----------------------------------------------------------------------------
   1.4 cat_grupos_respaldo — Agrupación lógica de fuentes de respaldo (§2, §9, §10)
        SQL RESTO | SQL FORTIA | MONGO | MICROSIP | MERCALTOS
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_grupos_respaldo', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_grupos_respaldo
    (
        GrupoRespaldoId   INT           NOT NULL IDENTITY(1,1),
        Codigo            VARCHAR(30)   NOT NULL,          -- SQL_RESTO / SQL_FORTIA / MONGO / MICROSIP / MERCALTOS
        Nombre            VARCHAR(80)   NOT NULL,
        Descripcion       VARCHAR(255)  NULL,
        Activo            BIT           NOT NULL CONSTRAINT DF_cat_grupos_Activo DEFAULT (1),
        FechaRegistro     DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_grupos_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_grupos_respaldo PRIMARY KEY CLUSTERED (GrupoRespaldoId),
        CONSTRAINT UQ_cat_grupos_respaldo_Codigo UNIQUE (Codigo)
    );
END
GO

/* ----------------------------------------------------------------------------
   1.5 cat_bases_datos  (§9, §10, §15) — Catálogo de bases/empresas a validar
        - RESTO: 41 bases (Lun-Sáb Diferencial / Dom Full)
        - FORTIA: 3 bases (Dom-Vie Diferencial / Sáb Full)
        - Extensible a MONGO (1), MICROSIP (63 empresas), MERCALTOS (1) mediante TipoFuente.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_bases_datos', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_bases_datos
    (
        BaseDatosId      INT           NOT NULL IDENTITY(1,1),
        GrupoRespaldoId  INT           NOT NULL,
        ServidorOrigenId INT           NULL,              -- Servidor donde se genera el respaldo
        NombreBase       VARCHAR(120)  NOT NULL,          -- DWCalzamoda / PROSUR_PRIME / ...
        TipoFuente       VARCHAR(20)   NOT NULL,          -- SQL / MONGO / MICROSIP / MERCALTOS
        TipoBackupPredeterminado VARCHAR(15) NOT NULL,    -- FULL / DIFERENCIAL (tipo de referencia)
        Observaciones    VARCHAR(255)  NULL,
        Activo           BIT           NOT NULL CONSTRAINT DF_cat_bases_Activo DEFAULT (1),
        FechaRegistro    DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_bases_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_bases_datos PRIMARY KEY CLUSTERED (BaseDatosId),
        CONSTRAINT UQ_cat_bases_datos_Nombre UNIQUE (GrupoRespaldoId, NombreBase),
        CONSTRAINT FK_cat_bases_Grupo FOREIGN KEY (GrupoRespaldoId) REFERENCES dbo.cat_grupos_respaldo (GrupoRespaldoId),
        CONSTRAINT FK_cat_bases_ServidorOrigen FOREIGN KEY (ServidorOrigenId) REFERENCES dbo.cat_servidores (ServidorId),
        CONSTRAINT CK_cat_bases_TipoFuente CHECK (TipoFuente IN ('SQL', 'MONGO', 'MICROSIP', 'MERCALTOS')),
        CONSTRAINT CK_cat_bases_TipoBackup CHECK (TipoBackupPredeterminado IN ('FULL', 'DIFERENCIAL'))
    );
END
GO

/* ----------------------------------------------------------------------------
   1.6 cat_tipos_incidencia  (§26) — Clasificación de incidencias
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_tipos_incidencia', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_tipos_incidencia
    (
        TipoIncidenciaId INT           NOT NULL IDENTITY(1,1),
        Codigo           VARCHAR(40)   NOT NULL,          -- RESPALDO_SQL / RESPALDO_MONGO / TRANSFERENCIA / JOB_SQL / ...
        Nombre           VARCHAR(80)   NOT NULL,
        Activo           BIT           NOT NULL CONSTRAINT DF_cat_tipos_inc_Activo DEFAULT (1),
        CONSTRAINT PK_cat_tipos_incidencia PRIMARY KEY CLUSTERED (TipoIncidenciaId),
        CONSTRAINT UQ_cat_tipos_incidencia_Codigo UNIQUE (Codigo)
    );
END
GO

/* ----------------------------------------------------------------------------
   1.7 cat_agentes  (§8) — Agentes (máquinas) que reportan al backend.
        - Un agente NO es una persona: no tiene rol Coordinador/Soporte/Admin.
        - ApiKeyHash: hash bcrypt de la API key del agente (nunca en claro).
        - La API key en claro se muestra UNA sola vez al crear el agente.
        - Agentes previstos: AGENTE_10.0.3.8, AGENTE_192.168.6.5
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_agentes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_agentes
    (
        AgenteId        INT           NOT NULL IDENTITY(1,1),
        Nombre          VARCHAR(50)   NOT NULL,          -- AGENTE_10.0.3.8 / AGENTE_192.168.6.5
        ApiKeyHash      VARCHAR(255)  NOT NULL,          -- hash bcrypt de la API key
        ServidorId      INT           NULL,          -- servidor donde vive el agente (Disco Checker §33)
        Activo          BIT           NOT NULL CONSTRAINT DF_cat_agentes_Activo DEFAULT (1),
        FechaRegistro   DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_agentes_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_agentes PRIMARY KEY CLUSTERED (AgenteId),
        CONSTRAINT UQ_cat_agentes_Nombre UNIQUE (Nombre),
        CONSTRAINT FK_cat_agentes_Servidor FOREIGN KEY (ServidorId) REFERENCES dbo.cat_servidores (ServidorId)
    );
END
GO

-- Migración idempotente (§33): BD creadas antes de ServidorId.
IF COL_LENGTH(N'dbo.cat_agentes', N'ServidorId') IS NULL
    ALTER TABLE dbo.cat_agentes ADD ServidorId INT NULL;
GO

IF OBJECT_ID(N'dbo.FK_cat_agentes_Servidor', N'F') IS NULL
    ALTER TABLE dbo.cat_agentes
        ADD CONSTRAINT FK_cat_agentes_Servidor FOREIGN KEY (ServidorId) REFERENCES dbo.cat_servidores (ServidorId);
GO

-- Vincular agentes a su servidor por NOMBRE (portable: los IDs difieren por
-- instalación — 10.0.3.8 es ServidorId 1 aquí, 4 en otra máquina). AGENTE_<IP>
-- se mapea al cat_servidores cuyo Nombre es esa IP.
UPDATE a SET ServidorId = s.ServidorId
FROM dbo.cat_agentes a
JOIN dbo.cat_servidores s ON s.Nombre = REPLACE(a.Nombre, 'AGENTE_', '')
WHERE a.ServidorId IS NULL;
GO

/* ----------------------------------------------------------------------------
   1.8 cat_jobs_monitoreados / cat_pasos_monitoreados — SQL Server Agent
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.cat_jobs_monitoreados', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_jobs_monitoreados
    (
        JobMonitoreadoId INT           NOT NULL IDENTITY(1,1),
        ServidorId       INT           NOT NULL,
        NombreJob        NVARCHAR(128) NOT NULL,
        Activo           BIT           NOT NULL CONSTRAINT DF_cat_jobs_Activo DEFAULT (1),
        CONSTRAINT PK_cat_jobs_monitoreados PRIMARY KEY CLUSTERED (JobMonitoreadoId),
        CONSTRAINT UQ_cat_jobs_monitoreados_ServidorNombre UNIQUE (ServidorId, NombreJob),
        CONSTRAINT FK_cat_jobs_monitoreados_Servidor FOREIGN KEY (ServidorId)
            REFERENCES dbo.cat_servidores (ServidorId)
    );
END
GO

IF OBJECT_ID(N'dbo.cat_pasos_monitoreados', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cat_pasos_monitoreados
    (
        PasoMonitoreadoId INT           NOT NULL IDENTITY(1,1),
        JobMonitoreadoId  INT           NOT NULL,
        StepId            INT           NOT NULL,
        NombrePaso        NVARCHAR(128) NOT NULL,
        Activo            BIT           NOT NULL CONSTRAINT DF_cat_pasos_Activo DEFAULT (1),
        CONSTRAINT PK_cat_pasos_monitoreados PRIMARY KEY CLUSTERED (PasoMonitoreadoId),
        CONSTRAINT UQ_cat_pasos_monitoreados_JobStep UNIQUE (JobMonitoreadoId, StepId),
        CONSTRAINT FK_cat_pasos_monitoreados_Job FOREIGN KEY (JobMonitoreadoId)
            REFERENCES dbo.cat_jobs_monitoreados (JobMonitoreadoId)
    );
END
GO

IF OBJECT_ID(N'dbo.pasos_horarios_esperados', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.pasos_horarios_esperados
    (
        PasoHorarioEsperadoId INT     NOT NULL IDENTITY(1,1),
        PasoMonitoreadoId     INT     NOT NULL,
        DiaSemana             TINYINT NOT NULL, -- 1=Lun ... 7=Dom
        DiaAplica             BIT     NOT NULL,
        HoraEsperada          TIME(0) NOT NULL,
        ToleranciaMinutos     INT     NOT NULL CONSTRAINT DF_pasos_horarios_Tolerancia DEFAULT (30),
        CONSTRAINT PK_pasos_horarios_esperados PRIMARY KEY CLUSTERED (PasoHorarioEsperadoId),
        CONSTRAINT UQ_pasos_horarios_PasoDiaHora UNIQUE (PasoMonitoreadoId, DiaSemana, HoraEsperada),
        CONSTRAINT FK_pasos_horarios_Paso FOREIGN KEY (PasoMonitoreadoId)
            REFERENCES dbo.cat_pasos_monitoreados (PasoMonitoreadoId),
        CONSTRAINT CK_pasos_horarios_Dia CHECK (DiaSemana BETWEEN 1 AND 7),
        CONSTRAINT CK_pasos_horarios_Tolerancia CHECK (ToleranciaMinutos >= 0)
    );
END
GO

IF OBJECT_ID(N'dbo.UQ_pasos_horarios_PasoDia', N'UQ') IS NOT NULL
    ALTER TABLE dbo.pasos_horarios_esperados DROP CONSTRAINT UQ_pasos_horarios_PasoDia;
GO
IF OBJECT_ID(N'dbo.UQ_pasos_horarios_PasoDiaHora', N'UQ') IS NULL
    ALTER TABLE dbo.pasos_horarios_esperados ADD CONSTRAINT UQ_pasos_horarios_PasoDiaHora
        UNIQUE (PasoMonitoreadoId, DiaSemana, HoraEsperada);
GO

-- ============================================================================
-- 2. CONFIGURACIÓN DE RESPALDOS  (§9, §10, §16, §31)
-- ============================================================================

/* ----------------------------------------------------------------------------
   2.1 rutas_origen_destino  (§9, §16, §30) — Rutas por base/empresa
        - Origen: donde el respaldo se genera (G:\TempRespSQLServer, ...).
        - Destino: ruta en el NAS (\\192.168.6.9\RespaldosBD2020\...).
        - Solo las rutas aquí registradas son tocadas por el sistema (§5).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.rutas_origen_destino', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.rutas_origen_destino
    (
        RutaOrigenDestinoId INT          NOT NULL IDENTITY(1,1),
        BaseDatosId         INT          NOT NULL,
        RutaOrigen          NVARCHAR(500) NOT NULL,
        RutaDestino         NVARCHAR(500) NOT NULL,
        ServidorDestinoId   INT          NULL,            -- Normalmente el NAS
        EliminarOrigenTrasTransferencia BIT NOT NULL CONSTRAINT DF_rutas_EliminarOrigen DEFAULT (1),
        Activo              BIT          NOT NULL CONSTRAINT DF_rutas_Activo DEFAULT (1),
        FechaRegistro       DATETIME2(0) NOT NULL CONSTRAINT DF_rutas_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_rutas_origen_destino PRIMARY KEY CLUSTERED (RutaOrigenDestinoId),
        CONSTRAINT UQ_rutas_origen_destino_Base UNIQUE (BaseDatosId),
        CONSTRAINT FK_rutas_Base FOREIGN KEY (BaseDatosId) REFERENCES dbo.cat_bases_datos (BaseDatosId),
        CONSTRAINT FK_rutas_ServidorDestino FOREIGN KEY (ServidorDestinoId) REFERENCES dbo.cat_servidores (ServidorId)
    );
END
GO

/* ----------------------------------------------------------------------------
   2.2 horarios_esperados  (§9, §29) — Cuándo y qué tipo se espera por base
        - Una fila por (Base, Día de la semana): Lun=1 ... Dom=7.
        - Permite expresar "Lun-Sáb Diferencial, Dom Full" y
          "Dom-Vie Diferencial, Sáb Full" sin lógica en código.
        - DiaAplica=0 indica NO APLICA (ej. Mercaltos no corre domingo).
        - ToleranciaMinutos configura la ventana nocturna (§29).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.horarios_esperados', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.horarios_esperados
    (
        HorarioEsperadoId INT           NOT NULL IDENTITY(1,1),
        BaseDatosId       INT           NOT NULL,
        DiaSemana         TINYINT       NOT NULL,          -- 1=Lun ... 7=Dom
        DiaAplica         BIT           NOT NULL CONSTRAINT DF_horarios_DiaAplica DEFAULT (1),
        TipoBackupEsperado VARCHAR(15)  NOT NULL,           -- FULL / DIFERENCIAL
        HoraEsperada      TIME(0)       NOT NULL,           -- 22:00
        ToleranciaMinutos INT           NOT NULL CONSTRAINT DF_horarios_Tolerancia DEFAULT (180), -- §29
        Activo            BIT           NOT NULL CONSTRAINT DF_horarios_Activo DEFAULT (1),
        FechaRegistro     DATETIME2(0)  NOT NULL CONSTRAINT DF_horarios_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_horarios_esperados PRIMARY KEY CLUSTERED (HorarioEsperadoId),
        CONSTRAINT UQ_horarios_esperados_BaseDia UNIQUE (BaseDatosId, DiaSemana),
        CONSTRAINT FK_horarios_Base FOREIGN KEY (BaseDatosId) REFERENCES dbo.cat_bases_datos (BaseDatosId),
        CONSTRAINT CK_horarios_DiaSemana CHECK (DiaSemana BETWEEN 1 AND 7),
        CONSTRAINT CK_horarios_TipoBackup CHECK (TipoBackupEsperado IN ('FULL', 'DIFERENCIAL'))
    );
END
GO

/* ----------------------------------------------------------------------------
   2.3 reglas_retencion  (§31) — Política de retención por grupo
        Actual: 3 meses, conservar 1 Full + 1 Diferencial por mes.
        La depuración del NAS se implementará en fase posterior.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.reglas_retencion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.reglas_retencion
    (
        ReglaRetencionId     INT          NOT NULL IDENTITY(1,1),
        GrupoRespaldoId      INT          NOT NULL,
        MesesRetencion       TINYINT      NOT NULL CONSTRAINT DF_retencion_Meses DEFAULT (3),
        ConservarFullPorMes  TINYINT      NOT NULL CONSTRAINT DF_retencion_Full DEFAULT (1),
        ConservarDiferencialPorMes TINYINT NOT NULL CONSTRAINT DF_retencion_Dif DEFAULT (1),
        DepuracionActiva     BIT          NOT NULL CONSTRAINT DF_retencion_Depuracion DEFAULT (0),
        Activo               BIT          NOT NULL CONSTRAINT DF_retencion_Activo DEFAULT (1),
        FechaRegistro        DATETIME2(0) NOT NULL CONSTRAINT DF_retencion_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_reglas_retencion PRIMARY KEY CLUSTERED (ReglaRetencionId),
        CONSTRAINT UQ_reglas_retencion_Grupo UNIQUE (GrupoRespaldoId),
        CONSTRAINT FK_retencion_Grupo FOREIGN KEY (GrupoRespaldoId) REFERENCES dbo.cat_grupos_respaldo (GrupoRespaldoId)
    );
END
GO

-- ============================================================================
-- 3. OPERACIÓN DIARIA  (§9, §11, §12, §26, §28)
-- ============================================================================

/* ----------------------------------------------------------------------------
   3.1 respaldos_ejecuciones — Resultado de la validación diaria por base
        - Es la fuente de la bitácora digital (§24): 41/41, 3/3, 62/63...
        - Idempotente por (Base, Fecha): reejecutar no duplica (§35).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.respaldos_ejecuciones', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.respaldos_ejecuciones
    (
        EjecucionId          BIGINT        NOT NULL IDENTITY(1,1),
        BaseDatosId          INT           NOT NULL,
        FechaEjecucion       DATE          NOT NULL,       -- Día operativo (respaldos de la noche)
        Estado               VARCHAR(15)   NOT NULL,       -- OK / ADVERTENCIA / ERROR / PENDIENTE / NO_APLICA
        TipoBackupEncontrado VARCHAR(15)   NULL,           -- FULL / DIFERENCIAL (si aplica)
        ArchivoEncontrado    NVARCHAR(500) NULL,
        TamanoBytes          BIGINT        NULL,
        FechaGeneracion      DATETIME2(0)  NULL,           -- Mtime del archivo en origen
        FueraDeHorario       BIT           NULL,           -- §9: generado fuera de la ventana esperada
        Detalle              NVARCHAR(MAX) NULL,        IncidenciaId         INT           NULL,           -- Si el error generó incidencia (FK declarada al final, ver sección 5)
        UsuarioRevisoId       INT           NULL,           -- Revisión humana (responsable del día)
        FechaRegistro        DATETIME2(0)  NOT NULL CONSTRAINT DF_ejecuciones_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_respaldos_ejecuciones PRIMARY KEY CLUSTERED (EjecucionId),
        CONSTRAINT UQ_respaldos_ejecuciones UNIQUE (BaseDatosId, FechaEjecucion),   -- Idempotencia
        CONSTRAINT FK_ejecuciones_Base FOREIGN KEY (BaseDatosId) REFERENCES dbo.cat_bases_datos (BaseDatosId),
        CONSTRAINT FK_ejecuciones_Usuario FOREIGN KEY (UsuarioRevisoId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT CK_ejecuciones_Estado CHECK (Estado IN ('OK', 'ADVERTENCIA', 'ERROR', 'PENDIENTE', 'NO_APLICA')),
        CONSTRAINT CK_ejecuciones_Tipo CHECK (TipoBackupEncontrado IS NULL OR TipoBackupEncontrado IN ('FULL', 'DIFERENCIAL'))
    );
END
GO

/* ----------------------------------------------------------------------------
   3.2 transferencias — Bitácora de transferencia al NAS (§11, §12, §30)
        - El origen se elimina ÚNICAMENTE cuando Estado = COMPLETADA y
          ValidacionOrigenEliminado = 1 (§30: nunca copiar->eliminar).
        - RetryNumber: intento actual (configurable, §13).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.transferencias', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.transferencias
    (
        TransferenciaId      BIGINT        NOT NULL IDENTITY(1,1),
        EjecucionId          BIGINT        NOT NULL,
        BaseDatosId          INT           NOT NULL,
        FechaTransferencia   DATETIME2(0)  NOT NULL CONSTRAINT DF_transferencias_Fecha DEFAULT (SYSDATETIME()),
        RetryNumber          TINYINT       NOT NULL CONSTRAINT DF_transferencias_Retry DEFAULT (1),
        Estado               VARCHAR(20)   NOT NULL,       -- EN_PROGRESO / COMPLETADA / FALLIDA / PENDIENTE
        RutaOrigenEfectiva   NVARCHAR(500) NOT NULL,
        RutaDestinoEfectiva  NVARCHAR(500) NOT NULL,
        TamanoOrigenBytes    BIGINT        NULL,
        TamanoDestinoBytes   BIGINT        NULL,
        HashOrigen           CHAR(64)      NULL,           -- SHA-256 si aplica (§12)
        HashDestino          CHAR(64)      NULL,
        HashCoincide         BIT           NULL,
        OrigenEliminado      BIT           NOT NULL CONSTRAINT DF_transferencias_OrigenEliminado DEFAULT (0), -- §30
        ErrorDetalle         NVARCHAR(MAX) NULL,
        IncidenciaId         INT           NULL,           -- FK declarada al final, ver sección 5
        FechaRegistro        DATETIME2(0)  NOT NULL CONSTRAINT DF_transferencias_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_transferencias PRIMARY KEY CLUSTERED (TransferenciaId),
        CONSTRAINT FK_transferencias_Ejecucion FOREIGN KEY (EjecucionId) REFERENCES dbo.respaldos_ejecuciones (EjecucionId),
        CONSTRAINT FK_transferencias_Base FOREIGN KEY (BaseDatosId) REFERENCES dbo.cat_bases_datos (BaseDatosId),
        CONSTRAINT CK_transferencias_Estado CHECK (Estado IN ('EN_PROGRESO', 'COMPLETADA', 'FALLIDA', 'PENDIENTE'))
    );
END
GO

/* ----------------------------------------------------------------------------
   3.3 incidencias  (§26) — Cada error detectado genera una incidencia.
        - Estado: ABIERTA / EN_PROCESO / RESUELTA
        - DetectadaPor: SISTEMA / USUARIO
        - ResponsableDiaId: responsable del día (concepto distinto de quien interviene).
        - NumeroIncidencia = folio visible (#000125) derivado del Id.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.incidencias', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.incidencias
    (
        IncidenciaId        INT           NOT NULL IDENTITY(1,1),
        TipoIncidenciaId    INT           NOT NULL,
        ServidorId          INT           NULL,
        BaseDatosId         INT           NULL,
        FechaIncidencia     DATE          NOT NULL,
        Estado              VARCHAR(15)   NOT NULL CONSTRAINT DF_incidencias_Estado DEFAULT ('ABIERTA'),
        DetectadaPor        VARCHAR(10)   NOT NULL CONSTRAINT DF_incidencias_DetectadaPor DEFAULT ('SISTEMA'),
        Problema            NVARCHAR(500) NOT NULL,        -- Ej.: "No se encontró respaldo diferencial."
        Detalle             NVARCHAR(MAX) NULL,
        ResponsableDiaId    INT           NULL,            -- §21: responsable del día
        UsuarioAtendioId    INT           NULL,            -- Quien realizó la intervención
        AccionTomada        NVARCHAR(MAX) NULL,            -- Intervención realizada
        Resultado           VARCHAR(15)   NULL,            -- CORRECTO / INCORRECTO / EN_PROCESO
        FechaResolucion     DATETIME2(0)  NULL,
        FechaRegistro       DATETIME2(0)  NOT NULL CONSTRAINT DF_incidencias_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_incidencias PRIMARY KEY CLUSTERED (IncidenciaId),
        CONSTRAINT FK_incidencias_Tipo FOREIGN KEY (TipoIncidenciaId) REFERENCES dbo.cat_tipos_incidencia (TipoIncidenciaId),
        CONSTRAINT FK_incidencias_Servidor FOREIGN KEY (ServidorId) REFERENCES dbo.cat_servidores (ServidorId),
        CONSTRAINT FK_incidencias_Base FOREIGN KEY (BaseDatosId) REFERENCES dbo.cat_bases_datos (BaseDatosId),
        CONSTRAINT FK_incidencias_ResponsableDia FOREIGN KEY (ResponsableDiaId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT FK_incidencias_Atendio FOREIGN KEY (UsuarioAtendioId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT CK_incidencias_Estado CHECK (Estado IN ('ABIERTA', 'EN_PROCESO', 'RESUELTA')),
        CONSTRAINT CK_incidencias_DetectadaPor CHECK (DetectadaPor IN ('SISTEMA', 'USUARIO')),
        CONSTRAINT CK_incidencias_Resultado CHECK (Resultado IS NULL OR Resultado IN ('CORRECTO', 'INCORRECTO', 'EN_PROCESO'))
    );
END
GO

/* ----------------------------------------------------------------------------
   3.4 acciones_incidencia  (§21, §27) — Trazabilidad de cada intervención.
        - Una incidencia puede tener varias acciones.
        - UsuarioId: quien intervino (puede ser distinto del responsable del día).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.acciones_incidencia', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.acciones_incidencia
    (
        AccionIncidenciaId INT           NOT NULL IDENTITY(1,1),
        IncidenciaId       INT           NOT NULL,
        UsuarioId          INT           NOT NULL,
        FechaAccion        DATETIME2(0)  NOT NULL CONSTRAINT DF_acciones_Fecha DEFAULT (SYSDATETIME()),
        Descripcion        NVARCHAR(MAX) NOT NULL,
        Resultado          VARCHAR(15)   NULL,             -- CORRECTO / INCORRECTO / EN_PROCESO
        CONSTRAINT PK_acciones_incidencia PRIMARY KEY CLUSTERED (AccionIncidenciaId),
        CONSTRAINT FK_acciones_Incidencia FOREIGN KEY (IncidenciaId) REFERENCES dbo.incidencias (IncidenciaId),
        CONSTRAINT FK_acciones_Usuario FOREIGN KEY (UsuarioId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT CK_acciones_Resultado CHECK (Resultado IS NULL OR Resultado IN ('CORRECTO', 'INCORRECTO', 'EN_PROCESO'))
    );
END
GO

/* ----------------------------------------------------------------------------
   3.5 alertas  (§28) — Bitácora de envío de correos.
        - Evita el envío excesivo: una alerta por entidad origen vía clave única.
        - Estado: ENVIADA / FALLIDA / PENDIENTE / SUPRIMIDA
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.alertas', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.alertas
    (
        AlertaId        INT            NOT NULL IDENTITY(1,1),
        IncidenciaId    INT            NULL,
        EjecucionId     BIGINT         NULL,
        LecturaDiscoId  BIGINT         NULL,
        TipoEvento      VARCHAR(30)    NOT NULL,           -- ERROR / ADVERTENCIA / INFO
        Asunto          NVARCHAR(200)  NOT NULL,
        Cuerpo          NVARCHAR(MAX)  NULL,
        Destinatarios   NVARCHAR(500)  NULL,
        Estado          VARCHAR(15)    NOT NULL CONSTRAINT DF_alertas_Estado DEFAULT ('ENVIADA'),
        ErrorDetalle    NVARCHAR(MAX)  NULL,
        FechaEnvio      DATETIME2(0)   NULL,
        FechaRegistro   DATETIME2(0)   NOT NULL CONSTRAINT DF_alertas_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_alertas PRIMARY KEY CLUSTERED (AlertaId),
        CONSTRAINT FK_alertas_Incidencia FOREIGN KEY (IncidenciaId) REFERENCES dbo.incidencias (IncidenciaId),
        CONSTRAINT FK_alertas_Ejecucion FOREIGN KEY (EjecucionId) REFERENCES dbo.respaldos_ejecuciones (EjecucionId),
        CONSTRAINT CK_alertas_Estado CHECK (Estado IN ('ENVIADA', 'FALLIDA', 'PENDIENTE', 'SUPRIMIDA')),
        CONSTRAINT CK_alertas_TipoEvento CHECK (TipoEvento IN ('ERROR', 'ADVERTENCIA', 'INFO'))
    );
END
GO

-- Migración idempotente (§28): FKs a la entidad origen de la alerta.
-- Nota: las PK referenciadas (EjecucionId/LecturaId) son BIGINT en este esquema;
-- SQL Server requiere el mismo tipo para crear la FK.
IF COL_LENGTH(N'dbo.alertas', N'EjecucionId') IS NULL
    ALTER TABLE dbo.alertas ADD EjecucionId BIGINT NULL;
GO

IF COL_LENGTH(N'dbo.alertas', N'ErrorDetalle') IS NULL
    ALTER TABLE dbo.alertas ADD ErrorDetalle NVARCHAR(MAX) NULL;
GO

-- Compatibilidad con BD creadas durante la implementación parcial anterior.
IF OBJECT_ID(N'dbo.FK_alertas_Lectura', N'F') IS NOT NULL
    ALTER TABLE dbo.alertas DROP CONSTRAINT FK_alertas_Lectura;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_alertas_ADVERTENCIA_Ejecucion' AND object_id = OBJECT_ID(N'dbo.alertas')
)
    DROP INDEX UQ_alertas_ADVERTENCIA_Ejecucion ON dbo.alertas;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_alertas_ADVERTENCIA_Lectura' AND object_id = OBJECT_ID(N'dbo.alertas')
)
    DROP INDEX UQ_alertas_ADVERTENCIA_Lectura ON dbo.alertas;
GO

IF COL_LENGTH(N'dbo.alertas', N'LecturaId') IS NOT NULL
   AND COL_LENGTH(N'dbo.alertas', N'LecturaDiscoId') IS NULL
    EXEC sp_rename 'dbo.alertas.LecturaId', 'LecturaDiscoId', 'COLUMN';
GO

IF COL_LENGTH(N'dbo.alertas', N'LecturaDiscoId') IS NULL
    ALTER TABLE dbo.alertas ADD LecturaDiscoId BIGINT NULL;
GO

-- Copia de datos solo si una BD intermedia quedó con AMBAS columnas (LecturaId
-- con datos + LecturaDiscoId NULL). Debe ir en SQL dinámico: si solo existe
-- LecturaId, el sp_rename previo ya la convirtió en LecturaDiscoId y este batch
-- no compilaría al referenciar la columna vieja (Msg 207 en parse/compilación).
IF COL_LENGTH(N'dbo.alertas', N'LecturaId') IS NOT NULL
   AND COL_LENGTH(N'dbo.alertas', N'LecturaDiscoId') IS NOT NULL
    EXEC(N'UPDATE dbo.alertas
             SET LecturaDiscoId = LecturaId
           WHERE LecturaDiscoId IS NULL
             AND LecturaId IS NOT NULL;');
GO

-- §28 anti-spam: barrera BD de deduplicación por ENTIDAD que originó la alerta.
-- Las ADVERTENCIAS no tienen IncidenciaId (no crean incidencia), por eso cada
-- alerta se deduplica por su referencia:
--   ERROR               -> IncidenciaId  (incidencia SISTEMA §26)
--   ADVERTENCIA respaldo -> EjecucionId  (idempotente por base+fecha)
--   ADVERTENCIA disco    -> LecturaDiscoId (idempotente por servidor+unidad+fecha)
-- Nota de equipo: columna nullable en índice único filtrado -> predicado explícito.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_alertas_ERROR_Incidencia' AND object_id = OBJECT_ID(N'dbo.alertas')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_alertas_ERROR_Incidencia
        ON dbo.alertas (IncidenciaId)
        WHERE TipoEvento = 'ERROR' AND IncidenciaId IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_alertas_ADVERTENCIA_Ejecucion' AND object_id = OBJECT_ID(N'dbo.alertas')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_alertas_ADVERTENCIA_Ejecucion
        ON dbo.alertas (TipoEvento, EjecucionId)
        WHERE EjecucionId IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_alertas_ADVERTENCIA_LecturaDisco' AND object_id = OBJECT_ID(N'dbo.alertas')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_alertas_ADVERTENCIA_LecturaDisco
        ON dbo.alertas (TipoEvento, LecturaDiscoId)
        WHERE LecturaDiscoId IS NOT NULL;
GO

/* ----------------------------------------------------------------------------
   3.6 responsables_dia  (§21) — Asignación automática del responsable del día.
        - Una fila por fecha (clave única Fecha).
        - OrigenAsignacion: AUTO (rotación) o MANUAL (reasignación por coordinador).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.responsables_dia', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.responsables_dia
    (
        ResponsableDiaId  INT           NOT NULL IDENTITY(1,1),
        Fecha             DATE          NOT NULL,
        UsuarioId         INT           NOT NULL,
        OrigenAsignacion  VARCHAR(10)   NOT NULL CONSTRAINT DF_responsables_Origen DEFAULT ('AUTO'),
        UsuarioReasignoId INT           NULL,              -- Coordinador que reasignó
        FechaAsignacion   DATETIME2(0)  NOT NULL CONSTRAINT DF_responsables_FechaAsignacion DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_responsables_dia PRIMARY KEY CLUSTERED (ResponsableDiaId),
        CONSTRAINT UQ_responsables_dia_Fecha UNIQUE (Fecha),
        CONSTRAINT FK_responsables_Usuario FOREIGN KEY (UsuarioId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT FK_responsables_Reasigno FOREIGN KEY (UsuarioReasignoId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT CK_responsables_Origen CHECK (OrigenAsignacion IN ('AUTO', 'MANUAL'))
    );
END
GO

/* ----------------------------------------------------------------------------
   3.7 rotacion  (§21) — Configuración de la rotación de responsables.
        - El coordinador define participantes, orden y suspensiones temporales.
        - El algoritmo de asignación recorre Orden saltando Suspendido=1.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.rotacion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.rotacion
    (
        RotacionId      INT           NOT NULL IDENTITY(1,1),
        UsuarioId       INT           NOT NULL,
        Orden           INT           NOT NULL,            -- Posición en la rotación (1, 2, 3...)
        Suspendido      BIT           NOT NULL CONSTRAINT DF_rotacion_Suspendido DEFAULT (0),
        FechaAlta       DATETIME2(0)  NOT NULL CONSTRAINT DF_rotacion_FechaAlta DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_rotacion PRIMARY KEY CLUSTERED (RotacionId),
        CONSTRAINT UQ_rotacion_Orden UNIQUE (Orden),
        CONSTRAINT FK_rotacion_Usuario FOREIGN KEY (UsuarioId) REFERENCES dbo.cat_usuarios (UsuarioId)
    );
END
GO

/* ----------------------------------------------------------------------------
   3.8 discos_lecturas  (§33 Disco Checker) — Lectura diaria de espacio en disco
        por servidor. La reporta el Disco Checker (agente), no el humano.
        UNIQUE (ServidorId, UnidadLetra, FechaLectura): misma idempotencia que
        respaldos_ejecuciones — reejecutar el checker actualiza en vez de duplicar.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.discos_lecturas', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.discos_lecturas
    (
        LecturaId       BIGINT        NOT NULL IDENTITY(1,1),
        ServidorId      INT           NOT NULL,
        UnidadLetra     VARCHAR(5)    NOT NULL,          -- 'C:', 'D:', 'G:' (o letra NAS)
        FechaLectura    DATE          NOT NULL,          -- día operativo de la lectura
        EspacioTotalGB  DECIMAL(10,2) NOT NULL,
        EspacioLibreGB  DECIMAL(10,2) NOT NULL,
        PorcentajeLibre DECIMAL(5,2)  NOT NULL,
        Estado          VARCHAR(15)   NOT NULL,          -- OK / ADVERTENCIA / ERROR
        Detalle         NVARCHAR(MAX) NULL,              -- trazabilidad del checker (§35)
        IncidenciaId    INT           NULL,              -- Si el ERROR generó incidencia (FK diferida, sección 5)
        FechaRegistro   DATETIME2(0)  NOT NULL CONSTRAINT DF_discos_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_discos_lecturas PRIMARY KEY CLUSTERED (LecturaId),
        CONSTRAINT UQ_discos_lecturas UNIQUE (ServidorId, UnidadLetra, FechaLectura),  -- Idempotencia
        CONSTRAINT FK_discos_Servidor FOREIGN KEY (ServidorId) REFERENCES dbo.cat_servidores (ServidorId),
        CONSTRAINT CK_discos_Estado CHECK (Estado IN ('OK', 'ADVERTENCIA', 'ERROR'))
    );
END
GO

-- Migración idempotente (§33): IncidenciaId en BD creadas antes.
IF COL_LENGTH(N'dbo.discos_lecturas', N'IncidenciaId') IS NULL
    ALTER TABLE dbo.discos_lecturas ADD IncidenciaId INT NULL;
GO

/* ----------------------------------------------------------------------------
   3.9 jobs_pasos_ejecuciones — Resultado diario de cada paso monitoreado.
        UNIQUE (PasoMonitoreadoId, FechaEjecucion, HoraEsperada): reejecutar
        una ventana actualiza su ejecución sin ocultar otras corridas del día.
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.jobs_pasos_ejecuciones', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.jobs_pasos_ejecuciones
    (
        EjecucionId       BIGINT        NOT NULL IDENTITY(1,1),
        PasoMonitoreadoId INT           NOT NULL,
        FechaEjecucion    DATE          NOT NULL,
        HoraEsperada      TIME(0)       NOT NULL,
        Estado            VARCHAR(10)   NOT NULL,
        FechaHoraReal     DATETIME2(0)  NULL,
        Mensaje           NVARCHAR(500) NULL,
        IncidenciaId      INT           NULL,
        CONSTRAINT PK_jobs_pasos_ejecuciones PRIMARY KEY CLUSTERED (EjecucionId),
        CONSTRAINT UQ_jobs_pasos_ejecuciones_PasoFechaHora UNIQUE (PasoMonitoreadoId, FechaEjecucion, HoraEsperada),
        CONSTRAINT FK_jobs_pasos_ejecuciones_Incidencia FOREIGN KEY (IncidenciaId)
            REFERENCES dbo.incidencias (IncidenciaId),
        CONSTRAINT FK_jobs_pasos_ejecuciones_Paso FOREIGN KEY (PasoMonitoreadoId)
            REFERENCES dbo.cat_pasos_monitoreados (PasoMonitoreadoId),
        CONSTRAINT CK_jobs_pasos_ejecuciones_Estado CHECK (Estado IN ('OK', 'ERROR', 'PENDIENTE', 'NO_APLICA'))
    );
END
GO

IF COL_LENGTH(N'dbo.jobs_pasos_ejecuciones', N'HoraEsperada') IS NULL
    ALTER TABLE dbo.jobs_pasos_ejecuciones ADD HoraEsperada TIME(0) NULL;
GO
IF OBJECT_ID(N'dbo.UQ_jobs_pasos_ejecuciones_PasoFecha', N'UQ') IS NOT NULL
    ALTER TABLE dbo.jobs_pasos_ejecuciones DROP CONSTRAINT UQ_jobs_pasos_ejecuciones_PasoFecha;
GO
IF OBJECT_ID(N'dbo.UQ_jobs_pasos_ejecuciones_PasoFechaHora', N'UQ') IS NULL
   AND NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.jobs_pasos_ejecuciones') AND name=N'HoraEsperada' AND is_nullable=1)
    ALTER TABLE dbo.jobs_pasos_ejecuciones ADD CONSTRAINT UQ_jobs_pasos_ejecuciones_PasoFechaHora
        UNIQUE (PasoMonitoreadoId, FechaEjecucion, HoraEsperada);
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_jobs_pasos_ejecuciones_Estado'
      AND parent_object_id = OBJECT_ID(N'dbo.jobs_pasos_ejecuciones')
      AND definition NOT LIKE '%NO_APLICA%'
)
    ALTER TABLE dbo.jobs_pasos_ejecuciones DROP CONSTRAINT CK_jobs_pasos_ejecuciones_Estado;
GO

IF OBJECT_ID(N'dbo.CK_jobs_pasos_ejecuciones_Estado', N'C') IS NULL
    ALTER TABLE dbo.jobs_pasos_ejecuciones
        ADD CONSTRAINT CK_jobs_pasos_ejecuciones_Estado
            CHECK (Estado IN ('OK', 'ERROR', 'PENDIENTE', 'NO_APLICA'));
GO

IF OBJECT_ID(N'dbo.FK_jobs_pasos_ejecuciones_Paso', N'F') IS NULL
    ALTER TABLE dbo.jobs_pasos_ejecuciones
        ADD CONSTRAINT FK_jobs_pasos_ejecuciones_Paso FOREIGN KEY (PasoMonitoreadoId)
            REFERENCES dbo.cat_pasos_monitoreados (PasoMonitoreadoId);
GO

-- ============================================================================
-- 4. HISTORIAL  (§27, §35)
-- ============================================================================

/* ----------------------------------------------------------------------------
   4.1 historial — Auditoría genérica de eventos y cambios de configuración.
        - Entidad/EntidadId: tabla y registro afectado.
        - TipoEvento: INSERT / UPDATE / DELETE / REASIGNACION / CAMBIO_CONFIG / ACCION
        - DatosAntes/DatosDespues: JSON de la fila antes y después (§27: consultas
          "¿quién intervino?", "¿cuánto tardó?", cambios de rotación).
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.historial', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.historial
    (
        HistorialId     BIGINT         NOT NULL IDENTITY(1,1),
        FechaEvento     DATETIME2(0)   NOT NULL CONSTRAINT DF_historial_Fecha DEFAULT (SYSDATETIME()),
        UsuarioId       INT            NULL,               -- NULL = evento del sistema automático
        Entidad         VARCHAR(80)    NOT NULL,           -- cat_rotacion, incidencias, ...
        EntidadId       INT            NULL,
        TipoEvento      VARCHAR(20)    NOT NULL,
        DatosAntes      NVARCHAR(MAX)  NULL,               -- JSON
        DatosDespues    NVARCHAR(MAX)  NULL,               -- JSON
        Descripcion     NVARCHAR(500)  NULL,
        CONSTRAINT PK_historial PRIMARY KEY CLUSTERED (HistorialId),
        CONSTRAINT FK_historial_Usuario FOREIGN KEY (UsuarioId) REFERENCES dbo.cat_usuarios (UsuarioId),
        CONSTRAINT CK_historial_TipoEvento CHECK (TipoEvento IN ('INSERT', 'UPDATE', 'DELETE', 'REASIGNACION', 'CAMBIO_CONFIG', 'ACCION'))
    );
END
GO

-- ============================================================================
-- 5. ÍNDICES COMPLEMENTARIOS (consultas del dashboard e histórico, §24, §25, §27)
-- ============================================================================

-- FKs de IncidenciaId: se declaran aquí porque incidencias se crea después de
-- respaldos_ejecuciones y transferencias (SQL Server no permite referencias hacia delante).
IF OBJECT_ID(N'dbo.FK_ejecuciones_Incidencia', N'F') IS NULL
    ALTER TABLE dbo.respaldos_ejecuciones
        ADD CONSTRAINT FK_ejecuciones_Incidencia FOREIGN KEY (IncidenciaId) REFERENCES dbo.incidencias (IncidenciaId);
GO

IF OBJECT_ID(N'dbo.FK_transferencias_Incidencia', N'F') IS NULL
    ALTER TABLE dbo.transferencias
        ADD CONSTRAINT FK_transferencias_Incidencia FOREIGN KEY (IncidenciaId) REFERENCES dbo.incidencias (IncidenciaId);
GO

IF OBJECT_ID(N'dbo.FK_discos_Incidencia', N'F') IS NULL
    ALTER TABLE dbo.discos_lecturas
        ADD CONSTRAINT FK_discos_Incidencia FOREIGN KEY (IncidenciaId) REFERENCES dbo.incidencias (IncidenciaId);
GO

IF OBJECT_ID(N'dbo.FK_alertas_Ejecucion', N'F') IS NULL
    ALTER TABLE dbo.alertas
        ADD CONSTRAINT FK_alertas_Ejecucion FOREIGN KEY (EjecucionId) REFERENCES dbo.respaldos_ejecuciones (EjecucionId);
GO

IF OBJECT_ID(N'dbo.FK_alertas_LecturaDisco', N'F') IS NULL
    ALTER TABLE dbo.alertas
        ADD CONSTRAINT FK_alertas_LecturaDisco FOREIGN KEY (LecturaDiscoId) REFERENCES dbo.discos_lecturas (LecturaId);
GO

-- §26: barrera de idempotencia para incidencias por SERVIDOR y TIPO
-- (DISCO_SERVIDOR / JOB_SQL_AGENT, BaseDatosId=NULL).
-- Los índices de respaldo cubren (Base, Fecha); en disco la entidad es el
-- SERVIDOR: (ServidorId, FechaIncidencia, SISTEMA). Dos (ABIERTA y EN_PROCESO)
-- por el mismo motivo que los de respaldo (SQL Server no permite IN en filtrado).
SET QUOTED_IDENTIFIER ON;  -- los índices filtrados (§26) lo requieren
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_DISCO_Abierta' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
AND NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE i.name = 'UQ_incidencias_DISCO_Abierta'
      AND i.object_id = OBJECT_ID(N'dbo.incidencias')
      AND c.name = 'TipoIncidenciaId'
)
    DROP INDEX UQ_incidencias_DISCO_Abierta ON dbo.incidencias;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_DISCO_EnProceso' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
AND NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
    JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
    WHERE i.name = 'UQ_incidencias_DISCO_EnProceso'
      AND i.object_id = OBJECT_ID(N'dbo.incidencias')
      AND c.name = 'TipoIncidenciaId'
)
    DROP INDEX UQ_incidencias_DISCO_EnProceso ON dbo.incidencias;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_DISCO_Abierta' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_DISCO_Abierta
        ON dbo.incidencias (ServidorId, TipoIncidenciaId, FechaIncidencia, DetectadaPor)
        WHERE DetectadaPor = 'SISTEMA' AND Estado = 'ABIERTA' AND BaseDatosId IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_DISCO_EnProceso' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_DISCO_EnProceso
        ON dbo.incidencias (ServidorId, TipoIncidenciaId, FechaIncidencia, DetectadaPor)
        WHERE DetectadaPor = 'SISTEMA' AND Estado = 'EN_PROCESO' AND BaseDatosId IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_respaldos_ejecuciones_FechaEstado' AND object_id = OBJECT_ID(N'dbo.respaldos_ejecuciones')
)
    CREATE NONCLUSTERED INDEX IX_respaldos_ejecuciones_FechaEstado
        ON dbo.respaldos_ejecuciones (FechaEjecucion, Estado) INCLUDE (BaseDatosId, TipoBackupEncontrado);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_respaldos_ejecuciones_Base' AND object_id = OBJECT_ID(N'dbo.respaldos_ejecuciones')
)
    CREATE NONCLUSTERED INDEX IX_respaldos_ejecuciones_Base
        ON dbo.respaldos_ejecuciones (BaseDatosId, FechaEjecucion DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_incidencias_Estado_Fecha' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE NONCLUSTERED INDEX IX_incidencias_Estado_Fecha
        ON dbo.incidencias (Estado, FechaIncidencia DESC) INCLUDE (TipoIncidenciaId, ServidorId, BaseDatosId);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_incidencias_Base' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE NONCLUSTERED INDEX IX_incidencias_Base
        ON dbo.incidencias (BaseDatosId, FechaIncidencia DESC);
GO

-- §26: barrera de idempotencia para incidencias AUTOMÁTICAS: solo una incidencia
-- abierta por (Base, Fecha, SISTEMA). SQL Server no permite IN/OR en el predicado
-- de un índice filtrado, por eso son dos (ABIERTA y EN_PROCESO).
-- Si el INSERT choca con estos índices, la API reutiliza la existente (§35).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_SISTEMA_Abierta' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_SISTEMA_Abierta
        ON dbo.incidencias (BaseDatosId, FechaIncidencia, DetectadaPor)
        WHERE DetectadaPor = 'SISTEMA' AND Estado = 'ABIERTA' AND BaseDatosId IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_incidencias_SISTEMA_EnProceso' AND object_id = OBJECT_ID(N'dbo.incidencias')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_incidencias_SISTEMA_EnProceso
        ON dbo.incidencias (BaseDatosId, FechaIncidencia, DetectadaPor)
        WHERE DetectadaPor = 'SISTEMA' AND Estado = 'EN_PROCESO' AND BaseDatosId IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_transferencias_Ejecucion' AND object_id = OBJECT_ID(N'dbo.transferencias')
)
    CREATE NONCLUSTERED INDEX IX_transferencias_Ejecucion
        ON dbo.transferencias (EjecucionId, Estado);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_historial_Entidad' AND object_id = OBJECT_ID(N'dbo.historial')
)
    CREATE NONCLUSTERED INDEX IX_historial_Entidad
        ON dbo.historial (Entidad, EntidadId, FechaEvento DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_historial_Fecha' AND object_id = OBJECT_ID(N'dbo.historial')
)
    CREATE NONCLUSTERED INDEX IX_historial_Fecha
        ON dbo.historial (FechaEvento DESC);
GO

-- ============================================================================
-- 6. SEED — CATÁLOGOS INICIALES (configurables desde BD, §35)
-- ============================================================================

-- 6.1 Roles (§22)
IF NOT EXISTS (SELECT 1 FROM dbo.cat_roles WHERE Codigo = 'COORDINADOR')
    INSERT INTO dbo.cat_roles (Codigo, Nombre, Descripcion) VALUES
        ('COORDINADOR',   'Coordinador',   'Administra rotación, reglas, incidencias y alertas'),
        ('SOPORTE',       'Soporte',       'Revisa bitácora, completa actividades y registra intervenciones'),
        ('ADMINISTRADOR', 'Administrador', 'Administra la configuración técnica del sistema');
GO

-- 6.2 Servidores (§2, §4, §5)
IF NOT EXISTS (SELECT 1 FROM dbo.cat_servidores WHERE Nombre = '10.0.3.8')
BEGIN
    INSERT INTO dbo.cat_servidores (Nombre, Descripcion, TipoServidor, EsNAS, EsOrigenRespaldo) VALUES
        (N'10.0.3.8',   N'AWS — SQL Server 2019, respaldos SQL/Mongo, Jobs, archivos', 'AWS',   0, 1),
        (N'10.0.1.91',  N'AWS — IIS, sistemas publicados, Task Scheduler, disco C:',  'AWS',   0, 0),
        (N'192.168.6.5',N'Local — Microsip (63 fbk), Mercaltos',                     'LOCAL', 0, 1),
        (N'192.168.6.9',N'NAS Synology DS918+ — RespaldosBD2020',                    'NAS',   1, 0);
END
GO

-- 6.3 Grupos de respaldo (§2, §9, §10)
IF NOT EXISTS (SELECT 1 FROM dbo.cat_grupos_respaldo WHERE Codigo = 'SQL_RESTO')
BEGIN
    INSERT INTO dbo.cat_grupos_respaldo (Codigo, Nombre, Descripcion) VALUES
        (N'SQL_RESTO',  N'SQL RESTO',   N'41 bases — Lun-Sáb Diferencial / Dom Full, G:\TempRespSQLServer'),
        (N'SQL_FORTIA', N'SQL FORTIA',  N'3 bases — Dom-Vie Diferencial / Sáb Full, G:\TempRespSQLServerFortia'),
        (N'MONGO',      N'MongoDB',     N'1 respaldo diario .zip — G:\BackupMongo\BackupMongoTemp'),
        (N'MICROSIP',   N'Microsip',    N'63 empresas .fbk — D:\Respaldos_Microsip\Local\Local'),
        (N'MERCALTOS',  N'Mercaltos',   N'1 archivo diario (excepto domingo) — H:\Mi unidad\Comercialtos\Respaldos');
END
GO

-- 6.4 Tipos de incidencia (§26)
IF NOT EXISTS (SELECT 1 FROM dbo.cat_tipos_incidencia WHERE Codigo = 'RESPALDO_SQL')
BEGIN
    INSERT INTO dbo.cat_tipos_incidencia (Codigo, Nombre) VALUES
        (N'RESPALDO_SQL',    N'Respaldo SQL'),
        (N'RESPALDO_MONGO',  N'Respaldo MongoDB'),
        (N'RESPALDO_MICROSIP', N'Respaldo Microsip'),
        (N'RESPALDO_MERCALTOS', N'Respaldo Mercaltos'),
        (N'TRANSFERENCIA',   N'Transferencia a NAS'),
        (N'JOB_SQL',         N'Job de SQL Server'),
        (N'ARCHIVO_CONFIANZA', N'Archivo de confianza'),
        (N'DISCO_SERVIDOR',  N'Espacio en disco'),
        (N'CONECTIVIDAD',    N'Conectividad / VPN'),
        (N'OTRO',            N'Otro');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.cat_tipos_incidencia WHERE Codigo = 'JOB_SQL_AGENT')
    INSERT INTO dbo.cat_tipos_incidencia (Codigo, Nombre)
    VALUES (N'JOB_SQL_AGENT', N'Job de SQL Server Agent');
GO

-- 6.5 Jobs y pasos SQL Agent de 10.0.3.8 (11 jobs / 49 pasos)
DECLARE @ServidorJobsId INT = (
    SELECT ServidorId FROM dbo.cat_servidores WHERE Nombre = N'10.0.3.8'
);

IF @ServidorJobsId IS NULL
    THROW 50001, 'No existe el servidor 10.0.3.8 para sembrar SQL Agent.', 1;

INSERT INTO dbo.cat_jobs_monitoreados (ServidorId, NombreJob, Activo)
SELECT @ServidorJobsId, v.NombreJob, 1
FROM (VALUES
    (N'CAJAAHORROS'),
    (N'Calzamoda'),
    (N'Chesa'),
    (N'ChesaDia'),
    (N'CincoPinos'),
    (N'ConciliadorCFDI'),
    (N'DepurarLogs'),
    (N'Insumos'),
    (N'NOTIFICACION CAJA AHORROS'),
    (N'RIOVYNIL'),
    (N'ValidacionWhatsApp')
) AS v(NombreJob)
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.cat_jobs_monitoreados j
    WHERE j.ServidorId = @ServidorJobsId AND j.NombreJob = v.NombreJob
);

INSERT INTO dbo.cat_pasos_monitoreados (JobMonitoreadoId, StepId, NombrePaso, Activo)
SELECT j.JobMonitoreadoId, v.StepId, v.NombrePaso, 1
FROM (VALUES
    (N'CAJAAHORROS', 1, N'EstadoDeCuenta'),
    (N'Calzamoda', 1, N'NotificaciónDiferenciaInvParciales'),
    (N'Calzamoda', 2, N'DashboardCalzamoda'),
    (N'Chesa', 1, N'BINuevo'),
    (N'Chesa', 2, N'InventariosChesa'),
    (N'Chesa', 3, N'EnvioCorreosSIVALE'),
    (N'Chesa', 4, N'SIVALE'),
    (N'Chesa', 5, N'APV´S comisiones'),
    (N'Chesa', 6, N'CONTACT_CENTER'),
    (N'Chesa', 7, N'PLANEACION_INVENTARIOS'),
    (N'ChesaDia', 1, N'BINuevo'),
    (N'ChesaDia', 2, N'InventariosChesa'),
    (N'CincoPinos', 1, N'BINuevo'),
    (N'CincoPinos', 2, N'BIPinotepa'),
    (N'ConciliadorCFDI', 1, N'Fortia'),
    (N'DepurarLogs', 1, N'DWCalzamoda'),
    (N'DepurarLogs', 2, N'servicedeskclz'),
    (N'DepurarLogs', 3, N'CincoPinos_DB'),
    (N'DepurarLogs', 4, N'BDAgencias'),
    (N'DepurarLogs', 5, N'CAJA_AHORROS'),
    (N'DepurarLogs', 6, N'RIOVINYL_BD'),
    (N'DepurarLogs', 7, N'CONCILIACIONES_CFDI'),
    (N'DepurarLogs', 8, N'Cubos_calzamoda'),
    (N'DepurarLogs', 9, N'Auditoria_db'),
    (N'DepurarLogs', 10, N'Fortia Blink'),
    (N'DepurarLogs', 11, N'Prosur Prime'),
    (N'DepurarLogs', 12, N'CiudadHidalgo'),
    (N'DepurarLogs', 13, N'servicedesk10_5'),
    (N'DepurarLogs', 14, N'DBFinanza'),
    (N'DepurarLogs', 15, N'CinciPinos'),
    (N'DepurarLogs', 16, N'FIDECOMISO PALENQUE'),
    (N'DepurarLogs', 17, N'CONCILIACIONES_CFDI_PRUEBA'),
    (N'DepurarLogs', 18, N'DBCONCILIADOR_CFDI'),
    (N'DepurarLogs', 19, N'DWAutoomotrizBI'),
    (N'DepurarLogs', 20, N'CERO PAPEL'),
    (N'DepurarLogs', 21, N'ARTEMISA'),
    (N'DepurarLogs', 22, N'SAT_EFOS_Sync_DB'),
    (N'DepurarLogs', 23, N'SIE_FORTIA_BD'),
    (N'DepurarLogs', 24, N'Objetivos'),
    (N'Insumos', 1, N'LineasTrab'),
    (N'Insumos', 2, N'Fortia BI'),
    (N'Insumos', 3, N'Seguridad'),
    (N'Insumos', 4, N'Actualizar tabla efos'),
    (N'Insumos', 5, N'Actualizar estatus proveedores'),
    (N'Insumos', 6, N'Baja Usuarios Microsip e Intelisis'),
    (N'Insumos', 7, N'ActualizarTrabajadoresCocina'),
    (N'NOTIFICACION CAJA AHORROS', 1, N'ENVIAR NOTIFICACION'),
    (N'RIOVYNIL', 1, N'Microsip'),
    (N'ValidacionWhatsApp', 1, N'Revisión de Envío de Notificaiones  WhatsApp')
) AS v(NombreJob, StepId, NombrePaso)
JOIN dbo.cat_jobs_monitoreados j
    ON j.ServidorId = @ServidorJobsId AND j.NombreJob = v.NombreJob
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.cat_pasos_monitoreados p
    WHERE p.JobMonitoreadoId = j.JobMonitoreadoId AND p.StepId = v.StepId
);

-- Frecuencia real leída de msdb.dbo.sysschedules el 2026-08-16.
-- MascaraDias usa el bitmask de SQL Agent: Dom=1, Lun=2, Mar=4, ... Sab=64.
-- Cada schedule habilitado conserva su propia ventana; un paso puede producir
-- varias ejecuciones el mismo día sin que una corrida oculte el resultado de otra.
INSERT INTO dbo.pasos_horarios_esperados
    (PasoMonitoreadoId, DiaSemana, DiaAplica, HoraEsperada, ToleranciaMinutos)
SELECT p.PasoMonitoreadoId, d.DiaSemana,
       CONVERT(bit, CASE WHEN (s.MascaraDias & d.BitSqlAgent) <> 0 THEN 1 ELSE 0 END),
       s.HoraEsperada, 30
FROM (VALUES
    (N'CAJAAHORROS', 127, CAST('14:30' AS TIME(0))),
    (N'CAJAAHORROS', 127, CAST('23:30' AS TIME(0))),
    (N'Calzamoda', 127, CAST('07:00' AS TIME(0))),
    (N'Chesa', 127, CAST('04:00' AS TIME(0))),
    (N'ChesaDia', 127, CAST('14:35' AS TIME(0))),
    (N'CincoPinos', 127, CAST('22:00' AS TIME(0))),
    (N'ConciliadorCFDI', 127, CAST('01:00' AS TIME(0))),
    (N'DepurarLogs', 13, CAST('21:00' AS TIME(0))),
    (N'Insumos', 127, CAST('04:00' AS TIME(0))),
    (N'Insumos', 127, CAST('12:10' AS TIME(0))),
    (N'NOTIFICACION CAJA AHORROS', 127, CAST('09:00' AS TIME(0))),
    (N'NOTIFICACION CAJA AHORROS', 127, CAST('16:00' AS TIME(0))),
    (N'RIOVYNIL', 127, CAST('01:00' AS TIME(0))),
    (N'ValidacionWhatsApp', 126, CAST('10:00' AS TIME(0))),
    (N'ValidacionWhatsApp', 126, CAST('12:00' AS TIME(0)))
) AS s(NombreJob, MascaraDias, HoraEsperada)
JOIN dbo.cat_jobs_monitoreados j
    ON j.ServidorId = @ServidorJobsId AND j.NombreJob = s.NombreJob
JOIN dbo.cat_pasos_monitoreados p ON p.JobMonitoreadoId = j.JobMonitoreadoId
CROSS JOIN (VALUES
    (1, 2), (2, 4), (3, 8), (4, 16), (5, 32), (6, 64), (7, 1)
) AS d(DiaSemana, BitSqlAgent)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.pasos_horarios_esperados h
    WHERE h.PasoMonitoreadoId = p.PasoMonitoreadoId AND h.DiaSemana = d.DiaSemana
      AND h.HoraEsperada = s.HoraEsperada
);

-- Migración de ejecuciones creadas antes de que HoraEsperada formara parte
-- de su identidad. Se asocian a la última ventana configurada de ese día.
IF EXISTS (SELECT 1 FROM dbo.jobs_pasos_ejecuciones WHERE HoraEsperada IS NULL)
BEGIN
    UPDATE e SET HoraEsperada = x.HoraEsperada
    FROM dbo.jobs_pasos_ejecuciones e
    CROSS APPLY (
        SELECT MAX(h.HoraEsperada) AS HoraEsperada
        FROM dbo.pasos_horarios_esperados h
        WHERE h.PasoMonitoreadoId = e.PasoMonitoreadoId
          AND h.DiaSemana = (DATEDIFF(DAY, CONVERT(date, '19000101', 112), e.FechaEjecucion) % 7) + 1
    ) x
    WHERE e.HoraEsperada IS NULL;
END
IF EXISTS (SELECT 1 FROM dbo.jobs_pasos_ejecuciones WHERE HoraEsperada IS NULL)
    THROW 50002, 'No fue posible asociar HoraEsperada a ejecuciones existentes.', 1;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.jobs_pasos_ejecuciones') AND name=N'HoraEsperada' AND is_nullable=1)
BEGIN
    IF OBJECT_ID(N'dbo.UQ_jobs_pasos_ejecuciones_PasoFechaHora', N'UQ') IS NOT NULL
        ALTER TABLE dbo.jobs_pasos_ejecuciones DROP CONSTRAINT UQ_jobs_pasos_ejecuciones_PasoFechaHora;
    ALTER TABLE dbo.jobs_pasos_ejecuciones ALTER COLUMN HoraEsperada TIME(0) NOT NULL;
END
IF OBJECT_ID(N'dbo.UQ_jobs_pasos_ejecuciones_PasoFechaHora', N'UQ') IS NULL
    ALTER TABLE dbo.jobs_pasos_ejecuciones ADD CONSTRAINT UQ_jobs_pasos_ejecuciones_PasoFechaHora
        UNIQUE (PasoMonitoreadoId, FechaEjecucion, HoraEsperada);
GO

-- 6.6 Bases FORTIA (§10) — las 3 bases con su configuración completa
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos b JOIN dbo.cat_grupos_respaldo g ON b.GrupoRespaldoId = g.GrupoRespaldoId WHERE g.Codigo = 'SQL_FORTIA')
BEGIN
    DECLARE @GrupoFortiaId INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'SQL_FORTIA');
    DECLARE @Servidor38Id  INT = (SELECT ServidorId   FROM dbo.cat_servidores WHERE Nombre = '10.0.3.8');
    DECLARE @NASSynologyId INT = (SELECT ServidorId   FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');

    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    SELECT @GrupoFortiaId, @Servidor38Id, x.NombreBase, N'SQL', N'DIFERENCIAL'
    FROM (VALUES
        (N'PROSUR_PRIME'),
        (N'PROSUR_PRIME_BLINK'),
        (N'PROSUR_PRIME_DATA')
    ) AS x(NombreBase)
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.cat_bases_datos b WHERE b.GrupoRespaldoId = @GrupoFortiaId AND b.NombreBase = x.NombreBase
    );

    -- Rutas (§5): G:\TempRespSQLServerFortia -> \\192.168.6.9\RespaldosBD2020\RESPALDOS SQL\SQL FORTIA\2026
    INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
    SELECT b.BaseDatosId,
           N'G:\TempRespSQLServerFortia',
           N'\\192.168.6.9\RespaldosBD2020\RESPALDOS SQL\SQL FORTIA\2026',
           @NASSynologyId,
           1
    FROM dbo.cat_bases_datos b WHERE b.GrupoRespaldoId = @GrupoFortiaId;

    -- Horarios (§10): Dom-Vie (7,1-5) DIFERENCIAL / Sáb (6) FULL, 22:00, tolerancia 3h
    INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
    SELECT b.BaseDatosId, d.DiaSemana, 1,
           CASE WHEN d.DiaSemana = 6 THEN 'FULL' ELSE 'DIFERENCIAL' END,
           CAST('22:00' AS TIME(0)), 180
    FROM dbo.cat_bases_datos b
    CROSS JOIN (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana)
    WHERE b.GrupoRespaldoId = @GrupoFortiaId;

    -- Retención (§31): 3 meses, 1 Full + 1 Diferencial por mes
    INSERT INTO dbo.reglas_retencion (GrupoRespaldoId, MesesRetencion, ConservarFullPorMes, ConservarDiferencialPorMes)
    VALUES (@GrupoFortiaId, 3, 1, 1);
END
GO

-- 6.6 Ejemplo RESTO (§9) — DWCalzamoda (las otras 40 bases se insertan en 6.8)
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DWCalzamoda')
BEGIN
    DECLARE @GrupoRestoId INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'SQL_RESTO');
    DECLARE @Servidor38bId INT = (SELECT ServidorId     FROM dbo.cat_servidores WHERE Nombre = '10.0.3.8');
    DECLARE @NASRestoId    INT = (SELECT ServidorId     FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');

    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38bId, N'DWCalzamoda', N'SQL', N'DIFERENCIAL');

    -- Capturamos el Id recién generado de forma robusta (sin depender de qué ocurra entre sentencias)
    DECLARE @BaseRestoEjemploId INT = SCOPE_IDENTITY();

    INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
    VALUES (@BaseRestoEjemploId,
            N'G:\TempRespSQLServer',
            N'\\192.168.6.9\RespaldosBD2020\RESPALDOS SQL\SQL RESTO BASES\2026',
            @NASRestoId, 1);

    -- Horarios (§9): Lun-Sáb (1-6) DIFERENCIAL / Dom (7) FULL
    INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
    SELECT @BaseRestoEjemploId, d.DiaSemana, 1,
           CASE WHEN d.DiaSemana = 7 THEN 'FULL' ELSE 'DIFERENCIAL' END,
           CAST('22:00' AS TIME(0)), 180
    FROM (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana);

    INSERT INTO dbo.reglas_retencion (GrupoRespaldoId, MesesRetencion, ConservarFullPorMes, ConservarDiferencialPorMes)
    VALUES (@GrupoRestoId, 3, 1, 1);
END
GO

-- ============================================================================
-- 6.8 Las 40 bases RESTO restantes (§9) — inventario de respaldos confirmado
--     (DWCalzamoda ya se insertó en 6.6; aquí SOLO las otras 40).
--     Cada base con IF NOT EXISTS por nombre para mantener la idempotencia
--     (§35), igual que el resto del script.
--     Patrón §9 del grupo: Lun-Sáb Diferencial / Dom Full -> predeterminado
--     DIFERENCIAL (los horarios por día se registran en horarios_esperados).
--     Al final: rutas_origen_destino por base (§5) con el mismo patrón de
--     carpeta que usó DWCalzamoda + subcarpeta {NombreBase}, y
--     EliminarOrigenTrasTransferencia=1 (todo en un solo batch: las variables
--     NO sobreviven a un GO, por eso no hay GO entre los INSERTs).
-- ============================================================================
DECLARE @GrupoRestoId INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'SQL_RESTO');
DECLARE @Servidor38Id INT = (SELECT ServidorId     FROM dbo.cat_servidores WHERE Nombre = '10.0.3.8');

IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'AUDITORIA_DB')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'AUDITORIA_DB', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'BDAgencias')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'BDAgencias', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'BDArtus')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'BDArtus', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CAJA_AHORROS')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CAJA_AHORROS', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CERO_PAPEL')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CERO_PAPEL', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CincoPinos')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CincoPinos', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CincoPinos_DB')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CincoPinos_DB', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CiudadHidalgo')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CiudadHidalgo', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'COMISIONES_GRAL')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'COMISIONES_GRAL', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CONCILIACIONES')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CONCILIACIONES', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CONCILIACIONES_CFDI')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CONCILIACIONES_CFDI', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CONCILIACIONES_CLZ')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CONCILIACIONES_CLZ', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'CZM_COTIZACIONES')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'CZM_COTIZACIONES', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBChatAPI')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBChatAPI', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBCONCILIADOR_BCO')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBCONCILIADOR_BCO', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBCONCILIADOR_CFDI')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBCONCILIADOR_CFDI', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBFinanza')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBFinanza', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBGRAPI')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBGRAPI', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBRRHH')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBRRHH', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DBTelemarketing')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DBTelemarketing', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DB_PROSUR_SERVICIOS')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DB_PROSUR_SERVICIOS', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DWAutomotrizBI')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DWAutomotrizBI', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DWCafi')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DWCafi', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DWCincoPinos')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DWCincoPinos', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'DWPinotepa')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'DWPinotepa', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'FIDEICOMISO_PALENQUE')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'FIDEICOMISO_PALENQUE', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'Insumos')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'Insumos', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'LineasTelefonicas')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'LineasTelefonicas', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'Pinotepa')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'Pinotepa', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'RIOVINYL')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'RIOVINYL', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'RIOVINYL_BD')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'RIOVINYL_BD', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SAT_EFOS_Sync_DB')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SAT_EFOS_Sync_DB', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SEGUIMIENTO_MINUTAS')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SEGUIMIENTO_MINUTAS', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SEGUIMIENTO_OBJETIVOS')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SEGUIMIENTO_OBJETIVOS', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SEGURIDAD_PROSUR')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SEGURIDAD_PROSUR', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SEGUROS')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SEGUROS', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'servicedesk10_5')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'servicedesk10_5', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SIE_servicedskclz')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SIE_servicedskclz', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SIE_FORTIA_BD')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SIE_FORTIA_BD', N'SQL', N'DIFERENCIAL');
IF NOT EXISTS (SELECT 1 FROM dbo.cat_bases_datos WHERE NombreBase = 'SIE_FORTIA_REP')
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoRestoId, @Servidor38Id, N'SIE_FORTIA_REP', N'SQL', N'DIFERENCIAL');

    -- Rutas (§5): G:\TempRespSQLServer -> \\192.168.6.9\RespaldosBD2020\RESPALDOS SQL\SQL RESTO BASES\{NombreBase}\
    -- (mismo patrón de carpeta que usó DWCalzamoda, con subcarpeta por base).
    DECLARE @NASRestoId INT = (SELECT ServidorId FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');
    INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
    SELECT b.BaseDatosId,
           N'G:\TempRespSQLServer',
           N'\\192.168.6.9\RespaldosBD2020\RESPALDOS SQL\SQL RESTO BASES\' + b.NombreBase + N'\',
           @NASRestoId,
           1
    FROM dbo.cat_bases_datos b
    JOIN dbo.cat_grupos_respaldo g ON g.GrupoRespaldoId = b.GrupoRespaldoId
    WHERE g.Codigo = 'SQL_RESTO'
      AND b.NombreBase IN (N'AUDITORIA_DB', N'BDAgencias', N'BDArtus', N'CAJA_AHORROS', N'CERO_PAPEL',
                           N'CincoPinos', N'CincoPinos_DB', N'CiudadHidalgo', N'COMISIONES_GRAL', N'CONCILIACIONES',
                           N'CONCILIACIONES_CFDI', N'CONCILIACIONES_CLZ', N'CZM_COTIZACIONES', N'DBChatAPI', N'DBCONCILIADOR_BCO',
                           N'DBCONCILIADOR_CFDI', N'DBFinanza', N'DBGRAPI', N'DBRRHH', N'DBTelemarketing',
                           N'DB_PROSUR_SERVICIOS', N'DWAutomotrizBI', N'DWCafi', N'DWCincoPinos', N'DWPinotepa',
                           N'FIDEICOMISO_PALENQUE', N'Insumos', N'LineasTelefonicas', N'Pinotepa', N'RIOVINYL',
                           N'RIOVINYL_BD', N'SAT_EFOS_Sync_DB', N'SEGUIMIENTO_MINUTAS', N'SEGUIMIENTO_OBJETIVOS', N'SEGURIDAD_PROSUR',
                           N'SEGUROS', N'servicedesk10_5', N'SIE_servicedskclz', N'SIE_FORTIA_BD', N'SIE_FORTIA_REP')
      AND NOT EXISTS (SELECT 1 FROM dbo.rutas_origen_destino r WHERE r.BaseDatosId = b.BaseDatosId);

    -- Horarios (§9): Lun-Sáb (1-6) DIFERENCIAL / Dom (7) FULL, 22:00,
    -- tolerancia 180 (misma ventana que DWCalzamoda). 40 bases x 7 dias = 280.
    -- Idempotente: solo para bases sin ningún horario registrado aún.
    INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
    SELECT b.BaseDatosId, d.DiaSemana, 1,
           CASE WHEN d.DiaSemana = 7 THEN 'FULL' ELSE 'DIFERENCIAL' END,
           CAST('22:00' AS TIME(0)), 180
    FROM dbo.cat_bases_datos b
    JOIN dbo.cat_grupos_respaldo g ON g.GrupoRespaldoId = b.GrupoRespaldoId
    CROSS JOIN (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana)
    WHERE g.Codigo = 'SQL_RESTO'
      AND b.NombreBase IN (N'AUDITORIA_DB', N'BDAgencias', N'BDArtus', N'CAJA_AHORROS', N'CERO_PAPEL',
                           N'CincoPinos', N'CincoPinos_DB', N'CiudadHidalgo', N'COMISIONES_GRAL', N'CONCILIACIONES',
                           N'CONCILIACIONES_CFDI', N'CONCILIACIONES_CLZ', N'CZM_COTIZACIONES', N'DBChatAPI', N'DBCONCILIADOR_BCO',
                           N'DBCONCILIADOR_CFDI', N'DBFinanza', N'DBGRAPI', N'DBRRHH', N'DBTelemarketing',
                           N'DB_PROSUR_SERVICIOS', N'DWAutomotrizBI', N'DWCafi', N'DWCincoPinos', N'DWPinotepa',
                           N'FIDEICOMISO_PALENQUE', N'Insumos', N'LineasTelefonicas', N'Pinotepa', N'RIOVINYL',
                           N'RIOVINYL_BD', N'SAT_EFOS_Sync_DB', N'SEGUIMIENTO_MINUTAS', N'SEGUIMIENTO_OBJETIVOS', N'SEGURIDAD_PROSUR',
                           N'SEGUROS', N'servicedesk10_5', N'SIE_servicedskclz', N'SIE_FORTIA_BD', N'SIE_FORTIA_REP')
      AND NOT EXISTS (SELECT 1 FROM dbo.horarios_esperados h WHERE h.BaseDatosId = b.BaseDatosId);
GO

-- ============================================================================
-- 6.9 Mongo (§10) — MONGO_BACKUP_DIARIO: 1 dump completo diario (.zip).
--     No aplica distinción Full/Diferencial -> TipoBackupPredeterminado='FULL'.
--     Mismo patrón de la 6.8: base con IF NOT EXISTS por nombre (§35) y
--     rutas/horarios con guard NOT EXISTS independiente, para que una
--     re-ejecución recupere lo que falte aunque la base ya exista.
-- ============================================================================
DECLARE @GrupoMongoId    INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'MONGO');
DECLARE @ServidorMongoId INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '10.0.3.8');
DECLARE @NASMongoId      INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');
DECLARE @BaseMongoId     INT = (SELECT BaseDatosId FROM dbo.cat_bases_datos WHERE NombreBase = 'MONGO_BACKUP_DIARIO');

IF @BaseMongoId IS NULL
BEGIN
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoMongoId, @ServidorMongoId, N'MONGO_BACKUP_DIARIO', N'MONGO', N'FULL');
    SET @BaseMongoId = SCOPE_IDENTITY();
END

-- Rutas (§5): G:\BackupMongo\BackupMongoTemp -> \\192.168.6.9\RespaldosBD2020\RESPALDOS MONGO\MONGO_BACKUP_DIARIO\
INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
SELECT @BaseMongoId,
       N'G:\BackupMongo\BackupMongoTemp',
       N'\\192.168.6.9\RespaldosBD2020\RESPALDOS MONGO\MONGO_BACKUP_DIARIO\',
       @NASMongoId, 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.rutas_origen_destino r WHERE r.BaseDatosId = @BaseMongoId);

-- Horarios (§9): dump completo diario -> FULL los 7 días, 23:59, tolerancia 180 (7 filas)
INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
SELECT @BaseMongoId, d.DiaSemana, 1, N'FULL', CAST('23:59' AS TIME(0)), 180
FROM (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana)
WHERE NOT EXISTS (SELECT 1 FROM dbo.horarios_esperados h WHERE h.BaseDatosId = @BaseMongoId);
GO

-- ============================================================================
-- 6.10 Microsip (§10) — MICROSIP_BACKUP_DIARIO: 1 respaldo completo diario (.fbk).
--      Servidor origen: 192.168.6.5 (agente 6.5 — Microsip/Mercaltos, §2).
--      No aplica distinción Full/Diferencial -> TipoBackupPredeterminado='FULL'.
--      Mismo patrón de la 6.9: base con IF NOT EXISTS por nombre (§35) y
--      ruta con guard NOT EXISTS independiente, para que una re-ejecución
--      recupere lo que falte aunque la base ya exista.
-- ============================================================================
DECLARE @GrupoMicrosipId    INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'MICROSIP');
DECLARE @ServidorMicrosipId INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '192.168.6.5');
DECLARE @NASMicrosipId      INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');
DECLARE @BaseMicrosipId     INT = (SELECT BaseDatosId FROM dbo.cat_bases_datos WHERE NombreBase = 'MICROSIP_BACKUP_DIARIO');

IF @BaseMicrosipId IS NULL
BEGIN
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoMicrosipId, @ServidorMicrosipId, N'MICROSIP_BACKUP_DIARIO', N'MICROSIP', N'FULL');
    SET @BaseMicrosipId = SCOPE_IDENTITY();
END

-- Rutas (§5): D:\Respaldos_Microsip\Local -> \\192.168.6.9\RespaldosBD2020\RESPALDOS MICROSIP\MICROSIP_BACKUP_DIARIO\
INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
SELECT @BaseMicrosipId,
       N'D:\Respaldos_Microsip\Local',
       N'\\192.168.6.9\RespaldosBD2020\RESPALDOS MICROSIP\MICROSIP_BACKUP_DIARIO\',
       @NASMicrosipId, 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.rutas_origen_destino r WHERE r.BaseDatosId = @BaseMicrosipId);

-- Horarios (§9): .7z completo diario -> FULL los 7 días, 22:00, tolerancia 180
-- (ventana 19:00-01:00, cubre el caso real de un .7z generado a las 00:32).
INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
SELECT @BaseMicrosipId, d.DiaSemana, 1, N'FULL', CAST('22:00' AS TIME(0)), 180
FROM (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana)
WHERE NOT EXISTS (SELECT 1 FROM dbo.horarios_esperados h WHERE h.BaseDatosId = @BaseMicrosipId);
GO
-- 6.11 Mercaltos (§10) — MERCALTOS_BACKUP_DIARIO: 1 respaldo completo diario.
--      Servidor origen: 192.168.6.5 (agente 6.5 — Microsip/Mercaltos, §2).
--      No aplica distinción Full/Diferencial -> TipoBackupPredeterminado='FULL'.
--      Mismo patrón de guards de 6.9/6.10: base con IF NOT EXISTS por nombre (§35)
--      y ruta con guard NOT EXISTS independiente (re-ejecución recupera lo que
--      falte aunque la base ya exista).
--      Mercaltos NO corre domingo (nota del grupo): DiaAplica=0 ese día.
-- ============================================================================
DECLARE @GrupoMercaltosId    INT = (SELECT GrupoRespaldoId FROM dbo.cat_grupos_respaldo WHERE Codigo = 'MERCALTOS');
DECLARE @ServidorMercaltosId INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '192.168.6.5');
DECLARE @NASMercaltosId      INT = (SELECT ServidorId      FROM dbo.cat_servidores WHERE Nombre = '192.168.6.9');
DECLARE @BaseMercaltosId     INT = (SELECT BaseDatosId FROM dbo.cat_bases_datos WHERE NombreBase = 'MERCALTOS_BACKUP_DIARIO');

IF @BaseMercaltosId IS NULL
BEGIN
    INSERT INTO dbo.cat_bases_datos (GrupoRespaldoId, ServidorOrigenId, NombreBase, TipoFuente, TipoBackupPredeterminado)
    VALUES (@GrupoMercaltosId, @ServidorMercaltosId, N'MERCALTOS_BACKUP_DIARIO', N'MERCALTOS', N'FULL');
    SET @BaseMercaltosId = SCOPE_IDENTITY();
END

-- Rutas (§5): H:\Mi unidad\Comercialtos\Respaldos -> \\192.168.6.9\RespaldosBD2020\RESPALDOS MERCALTOS\MERCALTOS_BACKUP_DIARIO\
INSERT INTO dbo.rutas_origen_destino (BaseDatosId, RutaOrigen, RutaDestino, ServidorDestinoId, EliminarOrigenTrasTransferencia)
SELECT @BaseMercaltosId,
       N'H:\Mi unidad\Comercialtos\Respaldos',
       N'\\192.168.6.9\RespaldosBD2020\RESPALDOS MERCALTOS\MERCALTOS_BACKUP_DIARIO\',
       @NASMercaltosId, 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.rutas_origen_destino r WHERE r.BaseDatosId = @BaseMercaltosId);

-- Horarios (§9): FULL diario 17:36, tolerancia 180 (ventana 14:36-20:36,
-- no cruza medianoche). Mercaltos NO corre domingo -> DiaAplica=0.
INSERT INTO dbo.horarios_esperados (BaseDatosId, DiaSemana, DiaAplica, TipoBackupEsperado, HoraEsperada, ToleranciaMinutos)
SELECT @BaseMercaltosId, d.DiaSemana,
       CASE WHEN d.DiaSemana = 7 THEN 0 ELSE 1 END,
       N'FULL', CAST('17:36' AS TIME(0)), 180
FROM (VALUES (1),(2),(3),(4),(5),(6),(7)) AS d(DiaSemana)
WHERE NOT EXISTS (SELECT 1 FROM dbo.horarios_esperados h WHERE h.BaseDatosId = @BaseMercaltosId);
GO
-- 6.7 Reglas de retención para grupos restantes (§31)
IF NOT EXISTS (SELECT 1 FROM dbo.reglas_retencion r JOIN dbo.cat_grupos_respaldo g ON r.GrupoRespaldoId = g.GrupoRespaldoId WHERE g.Codigo IN ('MONGO','MICROSIP','MERCALTOS'))
BEGIN
    INSERT INTO dbo.reglas_retencion (GrupoRespaldoId, MesesRetencion, ConservarFullPorMes, ConservarDiferencialPorMes)
    SELECT GrupoRespaldoId, 3, 1, 1
    FROM dbo.cat_grupos_respaldo
    WHERE Codigo IN ('MONGO', 'MICROSIP', 'MERCALTOS')
      AND GrupoRespaldoId NOT IN (SELECT GrupoRespaldoId FROM dbo.reglas_retencion);
END
GO

/* ============================================================================
   NOTAS FINALES

   Pendientes de fases posteriores (no bloquean este esquema):
     - catálogos Jobs, Archivos de confianza y Actividades manuales (Fase 7/8).
     - Mecanismo de auditoría por triggers (hoy se registra vía historial desde la API).

   Consultas de soporte (§27):
     - ¿Cuántas veces falló Microsip este mes?
         SELECT b.NombreBase, COUNT(*) FROM dbo.respaldos_ejecuciones e
         JOIN dbo.cat_bases_datos b ON b.BaseDatosId = e.BaseDatosId
         JOIN dbo.cat_grupos_respaldo g ON g.GrupoRespaldoId = b.GrupoRespaldoId
         WHERE g.Codigo = 'MICROSIP' AND e.Estado = 'ERROR'
           AND e.FechaEjecucion >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
         GROUP BY b.NombreBase ORDER BY COUNT(*) DESC;
     - ¿Qué base SQL falla más?  (mismo patrón con g.Codigo = 'SQL_RESTO')
     - ¿Quién atendió la incidencia?
         SELECT i.IncidenciaId, u.NombreCompleto
         FROM dbo.incidencias i
         JOIN dbo.acciones_incidencia a ON a.IncidenciaId = i.IncidenciaId
         JOIN dbo.cat_usuarios u ON u.UsuarioId = a.UsuarioId
         WHERE i.IncidenciaId = 125;
============================================================================ */
