from app.models.usuario import Usuario
from app.models.expediente import Expediente
from app.models.ubicacion import UbicacionFisica
from app.models.bitacora import Bitacora
from app.models.documento_expediente import DocumentoExpediente
from app.models.alerta import Alerta
from app.models.prestamo import PrestamoExpediente
from app.models.prestamo_grupal import PrestamoGrupo, PrestamoGrupoDetalle
from app.models.traslado_virtual import TrasladoVirtualExpediente
from app.models.importacion_portadores import ImportacionPortadores
from app.models.verificacion import VerificacionExpediente
from app.models.presencia import PresenciaUsuario
from app.models.anexo_rectificado import AnexoRectificado
from app.models.soporte_tecnico import ServicioSoporteTecnico
from app.models.control_acceso import AccesoCCT
from app.models.favorito_usuario import FavoritoUsuario
from app.models.analisis_documental import AnalisisDocumental
from app.models.lote_documental import SegmentoDocumental, AprendizajeDocumental, PatronAprendizajeDocumental
from app.models.coordinacion import (
    RegistroCoordinacion,
    PagoCoordinacion,
    MovimientoDispositivo,
    AnexoCoordinacion,
    ReporteMonitoreo,
    AnalisisRiesgo,
    DocumentoEmitido,
    ActividadCoordinacion,
    RemisionCoordinacion,
    RemisionExpediente,
)
