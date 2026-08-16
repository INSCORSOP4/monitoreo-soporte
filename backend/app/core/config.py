"""Configuración centralizada de la aplicación (§35: nada quemado en código).

Las credenciales y rutas se leen de variables de entorno / .env mediante
pydantic-settings. Nunca se colocan valores sensibles en el código fuente.
"""
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote_plus

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Aplicación ---
    app_name: str = "MONITOREO_SOPORTE API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    # TLS (HTTPS) en el propio servicio — §38: la VPN cifra entre redes, pero
    # X-Agent-Key viaja en el header y debe ir SIEMPRE por TLS. En producción
    # apuntar estos a los archivos del certificado; en dev pueden quedar vacíos.
    ssl_certfile: str = ""
    ssl_keyfile: str = ""
    # NoDecode evita que pydantic-settings intente json.loads sobre la lista;
    # el validador before convierte la cadena "a,b,c" del .env en lista.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- MONITOREO_SOPORTE (SQL Server 2019) ---
    # Si DB_ODBC_CONNECT está definida, tiene PRIORIDAD: es la connection string
    # ODBC completa (útil para LocalDB / instancias con nombres como
    # "(localdb)\MSSQLLocalDB" que son frágiles de escapar en la URL).
    db_odbc_connect: str = ""
    db_host: str = "10.0.3.8"
    db_port: int = 1433
    db_name: str = "MONITOREO_SOPORTE"
    db_user: str = "sa"
    db_password: str = ""
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_trust_server_certificate: str = "yes"

    # --- SEGURIDAD_PROSUR (solo lectura, §22) ---
    seguridad_host: str = "10.0.3.8"
    seguridad_port: int = 1433
    seguridad_db: str = "SEGURIDAD_PROSUR"
    seguridad_user: str = "sa"
    seguridad_password: str = ""
    seguridad_driver: str = "ODBC Driver 18 for SQL Server"
    seguridad_trust_server_certificate: str = "yes"

    # --- Disco Checker (§33) — umbrales GLOBALES de espacio libre, iguales para
    # todas las unidades de todos los servidores (política por .env, NO en BD;
    # si algún día se necesita un umbral por unidad, se agrega después).
    # Porcentaje libre bajo el cual el Disco Checker reporta ADVERTENCIA / ERROR.
    disk_warning_pct: int = 20
    disk_error_pct: int = 10

    # --- Autenticación (JWT) ---
    jwt_secret: str = "dev-only-secret-cambiar-en-produccion"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    auth_mode: str = "stub"  # stub (desarrollo) | seguridad (SEGURIDAD_PROSUR)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        """Acepta "a,b,c" del .env y la convierte en lista."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def _sqlserver_url(self, host: str, port: int, name: str, user: str, pwd: str, driver: str, trust: str) -> str:
        """Construye la cadena de conexión ODBC para SQL Server."""
        quoted_driver = quote_plus(driver)
        return (
            f"mssql+pyodbc://{user}:{quote_plus(pwd)}@{host}:{port}/{name}"
            f"?driver={quoted_driver}&TrustServerCertificate={trust}"
        )

    @property
    def database_url(self) -> str:
        """Cadena de conexión a MONITOREO_SOPORTE."""
        if self.db_odbc_connect:
            # pyodbc requiere Driver=; si la connection string no lo trae, lo inyectamos.
            conn = self.db_odbc_connect
            if "Driver=" not in conn and "DRIVER=" not in conn:
                conn = f"DRIVER={{{self.db_driver}}};{conn}"
            # mssql+pyodbc:///?odbc_connect=<connection string url-encoded>
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(conn)}"
        return self._sqlserver_url(
            self.db_host, self.db_port, self.db_name,
            self.db_user, self.db_password, self.db_driver,
            self.db_trust_server_certificate,
        )

    @property
    def seguridad_database_url(self) -> str:
        """Cadena de conexión a SEGURIDAD_PROSUR (solo lectura)."""
        return self._sqlserver_url(
            self.seguridad_host, self.seguridad_port, self.seguridad_db,
            self.seguridad_user, self.seguridad_password, self.seguridad_driver,
            self.seguridad_trust_server_certificate,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
