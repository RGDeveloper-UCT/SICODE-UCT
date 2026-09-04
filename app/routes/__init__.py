from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.expedientes import expedientes_bp
from app.routes.expedientes_admin import expedientes_admin_bp
from app.routes.expediente_fisico import expediente_fisico_bp
from app.routes.verificaciones import verificaciones_bp
from app.routes.bitacora import bitacora_bp
from app.routes.indice_documental import indice_documental_bp
from app.routes.alertas import alertas_bp
from app.routes.prestamos import prestamos_bp
from app.routes.prestamos_grupales import prestamos_grupales_bp
from app.routes.admin import admin_bp
from app.routes import admin_cola_recepcion as _admin_cola_recepcion
from app.routes.integridad import integridad_bp
from app.routes.busqueda import busqueda_bp
from app.routes.cuenta import cuenta_bp
from app.routes.pagos import pagos_bp
from app.routes.coordinacion import coordinacion_bp
from app.routes import coordinacion_expediente_completo as _coordinacion_expediente_completo
from app.routes import coordinacion_pendientes as _coordinacion_pendientes
from app.routes.coordinacion_export import coordinacion_export_bp
from app.routes.portadores import portadores_bp
from app.routes.uo import uo_bp
from app.routes.codigos_barras import codigos_barras_bp
from app.routes.rectificaciones import rectificaciones_bp
from app.routes.rectificacion_produccion import rectificacion_produccion_bp
from app.routes.soporte_tecnico import soporte_tecnico_bp
from app.routes.soporte_tecnico_pdf import soporte_tecnico_pdf_bp
from app.routes.control_accesos import control_accesos_bp
from app.routes.favoritos import favoritos_bp
from app.routes.analisis_documental import analisis_documental_bp
from app.routes.lote_documental import lote_documental_bp
from app.routes.sicode_ia import sicode_ia_bp
from app.routes.sicode_ia_jobs import sicode_ia_jobs_bp
from app.routes.cerebro_sicode import cerebro_sicode_bp
from app.routes.nexo_ia import nexo_ia_bp
from app.routes import nexo_admin_guard as _nexo_admin_guard
from app.routes.monitoreo_anexos import monitoreo_anexos_bp, instalar_registro_monitoreo
from app.routes.anexos_inteligentes import anexos_inteligentes_bp
from app.routes import coordinacion_monitoreo_masivo as _coordinacion_monitoreo_masivo
from app.routes import coordinacion_monitoreo_masivo_fisico as _coordinacion_monitoreo_masivo_fisico
from app.routes import aprendizaje_documental as _aprendizaje_documental
