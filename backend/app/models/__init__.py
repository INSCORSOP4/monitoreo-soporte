"""Modelos ORM de MONITOREO_SOPORTE.

Importar aquí todos los modelos para que queden registrados en Base.metadata.
"""
from app.models.catalogos import (  # noqa: F401
    CatAgente,
    CatBaseDatos,
    CatGrupoRespaldo,
    CatRol,
    CatServidor,
    CatTipoIncidencia,
    CatUsuario,
)
from app.models.configuracion import (  # noqa: F401
    HorarioEsperado,
    ReglaRetencion,
    RutaOrigenDestino,
)
from app.models.historial import Historial  # noqa: F401
from app.models.operacion import (  # noqa: F401
    AccionIncidencia,
    Alerta,
    DiscosLectura,
    Incidencia,
    RespaldoEjecucion,
    ResponsableDia,
    Rotacion,
    Transferencia,
)
