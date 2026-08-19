from collections import defaultdict

from app import db
from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.coordinacion import RegistroCoordinacion, RemisionExpediente
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


def dependencias_operativas(expediente_id):
    """Devuelve únicamente relaciones históricas/operativas que impiden borrado duro."""
    conteos = {
        "documentos": DocumentoExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "alertas": Alerta.query.filter_by(expediente_id=expediente_id).count(),
        "préstamos": PrestamoExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "verificaciones": VerificacionExpediente.query.filter_by(expediente_id=expediente_id).count(),
        "coordinación": RegistroCoordinacion.query.filter_by(expediente_id=expediente_id).count(),
        "remisiones": RemisionExpediente.query.filter_by(expediente_id=expediente_id).count(),
    }
    return {nombre: cantidad for nombre, cantidad in conteos.items() if cantidad}


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

    # Fase 1: liberar los códigos actualmente ocupados por los registros que cambiarán.
    for indice, cambio in enumerate(cambios, start=1):
        expediente = por_id[cambio["expediente_id"]]
        temporal = f"__TMP_SICODE_{expediente.id}_{indice}__"
        while temporal in usados:
            temporal += "X"
        usados.add(temporal)
        expediente.codigo_interno = temporal
    db.session.flush()

    # Fase 2: asignar los códigos canónicos vinculados al No. SP.
    for cambio in cambios:
        por_id[cambio["expediente_id"]].codigo_interno = cambio["nuevo"]
    db.session.flush()

    return cambios


def eliminar_registro_administrativo(expediente, usuario_id):
    """Elimina un registro erróneo sin destruir historial operativo y realinea códigos.

    Ubicación física vacía/administrativa puede eliminarse con el registro. La
    bitácora existente se conserva y se desvincula del FK antes del borrado.
    Cualquier documento, alerta, préstamo, verificación, Coordinación o remisión
    bloquea la operación para impedir pérdida de historia institucional.
    """
    bloqueos = dependencias_operativas(expediente.id)
    if bloqueos:
        raise EliminacionExpedienteBloqueada(bloqueos)

    datos_anteriores = {
        "id": expediente.id,
        "no_sp": expediente.no_sp,
        "codigo_interno": expediente.codigo_interno,
        "nombre_referencia": expediente.nombre_referencia,
        "expediente_fisico_registrado": expediente.expediente_fisico_registrado,
        "activo": expediente.activo,
    }
    expediente_id = expediente.id
    no_sp = expediente.no_sp
    codigo_interno = expediente.codigo_interno

    # Conservar auditoría previa sin dejar una FK apuntando a un registro eliminado.
    Bitacora.query.filter_by(expediente_id=expediente_id).update(
        {Bitacora.expediente_id: None},
        synchronize_session=False,
    )
    # La ubicación es un dato dependiente del registro maestro y no tiene valor
    # autónomo una vez que el registro erróneo deja de existir.
    UbicacionFisica.query.filter_by(expediente_id=expediente_id).delete(
        synchronize_session=False,
    )

    db.session.delete(expediente)
    db.session.flush()

    cambios = recalcular_codigos_sicode()

    registrar_bitacora(
        accion="ELIMINAR_EXPEDIENTE_ADMIN",
        modulo="Expedientes",
        descripcion=(
            f"Administrador eliminó definitivamente el registro SP {no_sp} "
            f"({codigo_interno}). Se realinearon {len(cambios)} códigos SICODE con su No. SP."
        ),
        usuario_id=usuario_id,
        expediente_id=None,
        entidad="Expediente",
        entidad_id=expediente_id,
        datos_anteriores=datos_anteriores,
        datos_posteriores={
            "eliminado": True,
            "codigos_realineados": cambios,
        },
        motivo="Eliminación administrativa de registro erróneo o de prueba.",
        commit=False,
    )

    return cambios
