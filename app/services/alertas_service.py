from datetime import date

from app import db
from app.models.alerta import Alerta
from app.models.prestamo import PrestamoExpediente

def crear_alerta_si_no_existe(
    expediente_id,
    tipo_alerta,
    titulo,
    descripcion=None,
    gravedad="Media",
    usuario_id=None,
    documento_id=None,
    origen="Automática",
):
    estados_abiertos = ["Abierta", "En revisión"]

    alerta_existente = (
        Alerta.query
        .filter(
            Alerta.expediente_id == expediente_id,
            Alerta.documento_id == documento_id,
            Alerta.tipo_alerta == tipo_alerta,
            Alerta.estado.in_(estados_abiertos),
        )
        .first()
    )

    if alerta_existente:
        return alerta_existente, False

    alerta = Alerta(
        expediente_id=expediente_id,
        documento_id=documento_id,
        tipo_alerta=tipo_alerta,
        titulo=titulo,
        descripcion=descripcion,
        gravedad=gravedad,
        estado="Abierta",
        origen=origen,
        creada_por_id=usuario_id,
    )

    db.session.add(alerta)
    db.session.commit()

    return alerta, True


def detectar_prestamos_vencidos(usuario_id=None):
    prestamos_vencidos = (
        PrestamoExpediente.query
        .filter(
            PrestamoExpediente.estado == "En préstamo",
            PrestamoExpediente.fecha_estimada_devolucion != None,
            PrestamoExpediente.fecha_estimada_devolucion < date.today(),
        )
        .all()
    )

    alertas_creadas = []

    for prestamo in prestamos_vencidos:
        expediente = prestamo.expediente

        alerta, creada = crear_alerta_si_no_existe(
            expediente_id=expediente.id,
            tipo_alerta="PRESTAMO_VENCIDO",
            titulo=f"Préstamo vencido: {expediente.no_sp}",
            descripcion=(
                f"El préstamo {prestamo.numero_control} del expediente No. de SP {expediente.no_sp} "
                f"tenía fecha estimada de devolución {prestamo.fecha_estimada_devolucion.strftime('%d/%m/%Y')} "
                f"y aún se encuentra en estado En préstamo."
            ),
            gravedad="Alta",
            usuario_id=usuario_id,
            origen="Automática",
        )

        if creada:
            alertas_creadas.append(alerta)

    return alertas_creadas
