import inspect

from app.routes import prestamos as prestamos_module


def _assert_bitacora_antes_del_commit(funcion, accion, requiere_flush=False):
    fuente = inspect.getsource(funcion)
    posicion_accion = fuente.index(f'accion="{accion}"')
    posicion_commit = fuente.index("db.session.commit()")

    assert posicion_accion < posicion_commit
    assert "commit=False" in fuente[posicion_accion:posicion_commit]
    if requiere_flush:
        posicion_flush = fuente.index("db.session.flush()")
        assert posicion_flush < posicion_accion


def test_prestamo_individual_y_bitacora_comparten_transaccion():
    _assert_bitacora_antes_del_commit(
        prestamos_module.nuevo,
        "REGISTRAR_PRESTAMO",
        requiere_flush=True,
    )


def test_traslado_virtual_y_bitacora_comparten_transaccion():
    _assert_bitacora_antes_del_commit(
        prestamos_module.nuevo_traslado_virtual,
        "REGISTRAR_TRASLADO_VIRTUAL",
        requiere_flush=True,
    )


def test_devolucion_y_bitacora_comparten_transaccion():
    _assert_bitacora_antes_del_commit(
        prestamos_module.devolver,
        "REGISTRAR_DEVOLUCION",
    )
