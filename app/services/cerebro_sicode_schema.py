import hashlib
from datetime import datetime

from sqlalchemy import inspect

from app import db
from app.models.bitacora import Bitacora


def inventariar_esquema_sicode(usuario_id=None):
    """Estudia la estructura completa de SICODE sin leer contenido de campos.

    Permite detectar que aparecieron nuevas tablas/campos tras una actualización y
    dejar esa evolución disponible para revisión técnica del desarrollador.
    """
    inspector = inspect(db.engine)
    tablas = []
    for nombre in sorted(inspector.get_table_names()):
        columnas = sorted(c["name"] for c in inspector.get_columns(nombre))
        tablas.append({"tabla": nombre, "columnas": columnas})

    plano = "|".join(f"{t['tabla']}:{','.join(t['columnas'])}" for t in tablas)
    firma = hashlib.sha256(plano.encode("utf-8")).hexdigest()[:24]
    columnas_total = sum(len(t["columnas"]) for t in tablas)

    anterior = (
        Bitacora.query
        .filter_by(accion="CEREBRO_SICODE_ESQUEMA", entidad="CerebroSicode")
        .order_by(Bitacora.id.desc())
        .first()
    )
    firma_anterior = None
    if anterior:
        firma_anterior = (anterior.datos_posteriores or {}).get("firma_esquema")

    cambio = bool(firma_anterior and firma_anterior != firma)
    primera_lectura = anterior is None
    if primera_lectura or cambio:
        db.session.add(Bitacora(
            usuario_id=usuario_id,
            accion="CEREBRO_SICODE_ESQUEMA",
            modulo="SICODE.IA",
            descripcion=(
                f"El cerebro inventarió la estructura de SICODE: {len(tablas)} tablas y {columnas_total} campos."
                + (" Se detectó un cambio de estructura respecto al inventario anterior." if cambio else " Inventario base creado.")
            ),
            entidad="CerebroSicode",
            entidad_id=firma,
            datos_posteriores={
                "firma_esquema": firma,
                "tablas_total": len(tablas),
                "columnas_total": columnas_total,
                "tablas": tablas,
                "cambio_detectado": cambio,
                "inventariado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            motivo="Inventario técnico automático; no contiene valores ni contenido documental",
        ))
        db.session.commit()

    return {
        "firma": firma,
        "tablas_total": len(tablas),
        "columnas_total": columnas_total,
        "cambio_detectado": cambio,
        "primera_lectura": primera_lectura,
    }
