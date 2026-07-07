from app import db
from app.models.alerta import Alerta

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
