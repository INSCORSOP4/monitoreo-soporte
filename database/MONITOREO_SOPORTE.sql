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
============================================================================ */

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
        Correo               VARCHAR(120)  NULL,
        RolId                INT           NOT NULL,
        Activo               BIT           NOT NULL CONSTRAINT DF_cat_usuarios_Activo DEFAULT (1),
        PasswordHash         VARCHAR(255)  NULL,          -- hash bcrypt (nunca contraseña en claro)
        DebeCambiarPassword  BIT           NOT NULL CONSTRAINT DF_cat_usuarios_DebeCambiar DEFAULT (1),
        FechaRegistro        DATETIME2(0)  NOT NULL CONSTRAINT DF_cat_usuarios_FechaRegistro DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_cat_usuarios PRIMARY KEY CLUSTERED (UsuarioId),
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
        - Evita el envío excesivo: una alerta por (TipoEvento, Incidencia, Fecha) vía clave única.
        - Estado: ENVIADA / FALLIDA / PENDIENTE / SUPRIMIDA
---------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.alertas', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.alertas
    (
        AlertaId        INT            NOT NULL IDENTITY(1,1),
        IncidenciaId    INT            NULL,
        EjecucionId     BIGINT         NULL,
        TipoEvento      VARCHAR(30)    NOT NULL,           -- ERROR / ADVERTENCIA / INFO
        Asunto          NVARCHAR(200)  NOT NULL,
        Cuerpo          NVARCHAR(MAX)  NULL,
        Destinatarios   NVARCHAR(500)  NULL,
        Estado          VARCHAR(15)    NOT NULL CONSTRAINT DF_alertas_Estado DEFAULT ('ENVIADA'),
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

CREATE NONCLUSTERED INDEX IX_respaldos_ejecuciones_FechaEstado
    ON dbo.respaldos_ejecuciones (FechaEjecucion, Estado) INCLUDE (BaseDatosId, TipoBackupEncontrado);
GO

CREATE NONCLUSTERED INDEX IX_respaldos_ejecuciones_Base
    ON dbo.respaldos_ejecuciones (BaseDatosId, FechaEjecucion DESC);
GO

CREATE NONCLUSTERED INDEX IX_incidencias_Estado_Fecha
    ON dbo.incidencias (Estado, FechaIncidencia DESC) INCLUDE (TipoIncidenciaId, ServidorId, BaseDatosId);
GO

CREATE NONCLUSTERED INDEX IX_incidencias_Base
    ON dbo.incidencias (BaseDatosId, FechaIncidencia DESC);
GO

CREATE NONCLUSTERED INDEX IX_transferencias_Ejecucion
    ON dbo.transferencias (EjecucionId, Estado);
GO

CREATE NONCLUSTERED INDEX IX_historial_Entidad
    ON dbo.historial (Entidad, EntidadId, FechaEvento DESC);
GO

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

-- 6.5 Bases FORTIA (§10) — las 3 bases con su configuración completa
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

-- 6.6 Ejemplo RESTO (§9) — DWCalzamoda (las 41 bases se cargan en data/seed_bases_res_to.sql)
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
     - data/seed_bases_res_to.sql   : carga de las 41 bases RESTO + horarios.
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
