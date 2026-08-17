"""Modelos ORM de MONITOREO_SOPORTE.

Importar aquí todos los modelos para que queden registrados en Base.metadata.
"""
from app.models.catalogos import (  # noqa: F401
    CatAgente,
    CatBaseDatos,
    CatGrupoRespaldo,
    CatJobMonitoreado,
    CatPasoMonitoreado,
    CatRol,
    CatServidor,
    CatTipoIncidencia,
    CatUsuario,
)
from app.models.configuracion import (  # noqa: F401
    HorarioEsperado,
    PasoHorarioEsperado,
    ReglaRetencion,
    RutaOrigenDestino,
)
from app.models.historial import Historial  # noqa: F401
from app.models.operacion import (  # noqa: F401
    AccionIncidencia,
    Alerta,
    DiscosLectura,
    Incidencia,
    JobsPasoEjecucion,
    RespaldoEjecucion,
    ResponsableDia,
    Rotacion,
    Transferencia,
)
