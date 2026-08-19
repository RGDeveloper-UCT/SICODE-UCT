from collections import defaultdict

from app import db
from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion, RemisionExpediente
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente
from app.models.ubicacion import UbicacionFisica
from app.models.verificacion import VerificacionExpediente
from app.services.bitacora_service import registrar_bitacora
from app.services.sp_service import normalizar_sp


class EliminacionExpedienteBloqueada(ValueError):
    def __init__(self, dependencias):
        self.dependencias = dependencias
        detalle = ", ".join(f"{nombre}: {cantidad}" for nombre, cantidad in dependencias.items())
        super().__init__(detalle)


class AlineacionCodigosError(ValueError):
    pass


def dependencias_purgables(expediente_id):
    """Historial local que un administrador puede purgar junto con un registro de prueba/error."""
    conteos = {
        "documentos": DocumentoExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "alertas": Alerta.query.filter_by(expediente_id=expediente_id).count(),
        "préstamos": PrestamoExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "verificaciones": VerificacionExpediente.query.filter_by(expediente_id=expediente_id).count(),
    }
    return {nombre: cantidad for nombre, cantidad in conteos.items() if cantidad}


def dependencias_criticas(expediente_id):
    """Relaciones institucionales que nunca se borran con la purga administrativa."""
    anexos_vinculados = (
        AnexoCoordinacion.query
        .join(DocumentoExpediente, AnexoCoordinacion.documento_expediente_id == DocumentoExpediente.id)
        .filter(DocumentoExpediente.expediente_id == expediente_id)
        .count()
    )
    conteos = {
        "coordinación": RegistroCoordinacion.query.filter_by(expediente_id=expediente_id).count(),
        "remisiones": RemisionExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "anexos de coordinación vinculados": anexos_vinculados,
    }
    return {nombre: cantidad for nombre, cantidad in conteos.items() if cantidad}


def dependencias_operativas(expediente_id):
    """Resumen completo de relaciones; útil para interfaz y auditoría."""
    return {**dependencias_purgables(expediente_id), **dependencias_criticas(expediente_id)}


def recalcular_codigos_sicode():
    """Alinea SICODE-UCT-NNNN con el No. SP numérico sin tocar IDs ni relaciones.

    La operación usa códigos temporales en una primera fase para respetar el
    índice UNIQUE mientras se corrige una cadena desplazada (por ejemplo,
    SP 2 = 0003, SP 3 = 0004, etc.).
    """
    expedientes = Expediente.query.order_by(Expediente.id.asc()).all()
    por_numero = defaultdict(list)
    no_numericos = []

    for expediente in expedientes:
        clave = normalizar_sp(expediente.no_sp)
        if clave and clave.isdigit():
            por_numero[int(clave)].append(expediente)
        else:
            no_numericos.append(expediente)

    duplicados = {numero: items for numero, items in por_numero.items() if len(items) > 1}
    if duplicados:
        detalle = ", ".join(
            f"SP {numero} ({'/'.join(str(item.id) for item in items)})"
            for numero, items in sorted(duplicados.items())
        )
        raise AlineacionCodigosError(
            "Existen SP equivalentes duplicados; no es seguro recalcular códigos: " + detalle
        )

    reservados = {item.codigo_interno: item for item in no_numericos}
    objetivos = {}
    for numero, items in por_numero.items():
        expediente = items[0]
        objetivo = f"SICODE-UCT-{numero:04d}"
        conflicto = reservados.get(objetivo)
        if conflicto and conflicto.id != expediente.id:
            raise AlineacionCodigosError(
                f"El código {objetivo} está reservado por el registro no numérico ID {conflicto.id}."
            )
        objetivos[expediente.id] = objetivo

    cambios = []
    for numero in sorted(por_numero):
        expediente = por_numero[numero][0]
        objetivo = objetivos[expediente.id]
        if expediente.codigo_interno != objetivo:
            cambios.append({
                "expediente_id": expediente.id,
                "no_sp": expediente.no_sp,
                "anterior": expediente.codigo_interno,
                "nuevo": objetivo,
            })

    if not cambios:
        return []

    por_id = {expediente.id: expediente for expediente in expedientes}
    usados = {expediente.codigo_interno for expediente in expedientes}

    # Fase 1: liberar códigos ocupados por registros que van a cambiar.
    for indice, cambio in enumerate(cambios, start=1):
        expediente = por_id[cambio["expediente_id"]]
        temporal = f"__TMP_SICODE_{expediente.id}_{indice}__"
        while temporal in usados:
            temporal += "X"
        usados.add(temporal)
        expediente.codigo_interno = temporal
    db.session.flush()

    # Fase 2: asignar códigos canónicos vinculados al No. SP.
    for cambio in cambios:
        por_id[cambio["expediente_id"]].codigo_interno = cambio["nuevo"]
    db.session.flush()

    return cambios


def eliminar_registro_administrativo(expediente, usuario_id):
    """Purga un registro de prueba/error y realinea los códigos SICODE.

    Solo un administrador llega a esta función desde la ruta protegida. El
    historial local (documentos, alertas, préstamos y verificaciones) se puede
    eliminar junto con el registro porque forma parte del mismo dato de prueba o
    captura errónea. En cambio, cualquier vínculo con Coordinación, remisiones o
    anexos de Coordinación bloquea la operación para proteger trazabilidad
    institucional real.
    """
    bloqueos = dependencias_criticas(expediente.id)
    if bloqueos:
        raise EliminacionExpedienteBloqueada(bloqueos)

    historial_purgado = dependencias_purgables(expediente.id)
    datos_anteriores = {
        "id": expediente.id,
        "no_sp": expediente.no_sp,
        "codigo_interno": expediente.codigo_interno,
        "nombre_referencia": expediente.nombre_referencia,
        "expediente_fisico_registrado": expediente.expediente_fisico_registrado,
        "activo": expediente.activo,
        "historial_local_purgado": historial_purgado,
    }
    expediente_id = expediente.id
    no_sp = expediente.no_sp
    codigo_interno = expediente.codigo_interno

    # La bitácora previa se conserva, únicamente se libera la FK al registro que
    # será eliminado. Así las acciones antiguas siguen visibles para auditoría.
    Bitacora.query.filter_by(expediente_id=expediente_id).update(
        {Bitacora.expediente_id: None},
        synchronize_session=False,
    )

    # Orden de borrado deliberado por llaves foráneas: alertas pueden apuntar a
    # documentos, por lo que se eliminan antes que el índice documental.
    Alerta.query.filter_by(expediente_id=expediente_id).delete(synchronize_session=False)
    PrestamoExpediente.query.filter_by(expediente_id=expediente_id).delete(synchronize_session=False)
    VerificacionExpediente.query.filter_by(expediente_id=expediente_id).delete(synchronize_session=False)
    DocumentoExpediente.query.filter_by(expediente_id=expediente_id).delete(synchronize_session=False)
    UbicacionFisica.query.filter_by(expediente_id=expediente_id).delete(synchronize_session=False)

    db.session.delete(expediente)
    db.session.flush()

    cambios = recalcular_codigos_sicode()

    registrar_bitacora(
        accion="PURGAR_EXPEDIENTE_ADMIN",
        modulo="Expedientes",
        descripcion=(
            f"Administrador eliminó definitivamente el registro SP {no_sp} "
            f"({codigo_interno}), incluyendo historial local asociado: "
            f"{historial_purgado or 'sin historial local'}. "
            f"Se realinearon {len(cambios)} códigos SICODE con su No. SP."
        ),
        usuario_id=usuario_id,
        expediente_id=None,
        entidad="Expediente",
        entidad_id=expediente_id,
        datos_anteriores=datos_anteriores,
        datos_posteriores={
            "eliminado": True,
            "historial_local_purgado": historial_purgado,
            "codigos_realineados": cambios,
        },
        motivo="Purga administrativa de registro de prueba o creado por error.",
        commit=False,
    )

    return cambios
