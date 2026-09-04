from __future__ import annotations

from sqlalchemy import text

from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion


_ADVISORY_NAMESPACE = 1397310287  # "SICO"; separa el lock de otros usos PostgreSQL.


class AnexoDuplicadoError(ValueError):
    """Se intentó individualizar dos veces el mismo número de anexo para un SP."""


def _numero_normalizado(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        numero = int(texto)
    except (TypeError, ValueError):
        return texto
    return str(numero)


def bloquear_y_validar_anexo_nuevo(session, anexo):
    """Serializa por expediente y rechaza duplicados incluso con dos usuarios simultáneos.

    PostgreSQL usa un advisory lock transaccional por expediente. Así dos
    estaciones que intenten guardar el mismo siguiente anexo no pueden superar
    ambas la comprobación. SQLite conserva la validación lógica para pruebas.
    """
    registro = anexo.registro
    if registro is None and anexo.registro_id is not None:
        registro = session.get(RegistroCoordinacion, anexo.registro_id)
    if registro is None or registro.expediente_id is None:
        return

    numero = _numero_normalizado(anexo.numero_anexo)
    if not numero:
        return
    anexo.numero_anexo = numero

    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :expediente_id)"),
            {"namespace": _ADVISORY_NAMESPACE, "expediente_id": int(registro.expediente_id)},
        )

    with session.no_autoflush:
        existente = (
            session.query(AnexoCoordinacion.id)
            .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
            .filter(
                RegistroCoordinacion.expediente_id == registro.expediente_id,
                AnexoCoordinacion.numero_anexo == numero,
            )
            .first()
        )

    if existente:
        raise AnexoDuplicadoError(
            f"El Anexo {numero} ya está individualizado para este SP. "
            "La operación fue cancelada para proteger la integridad documental."
        )
