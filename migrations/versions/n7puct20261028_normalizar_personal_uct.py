"""Personal UCT: normalizar nombres y apellidos existentes a mayúsculas.

Revision ID: n7puct20261028
Revises: m6c09a20261028

Esta revisión no cambia IDs ni relaciones con inventario, soporte o Agenda.
"""
from alembic import op
import sqlalchemy as sa

revision = "n7puct20261028"
down_revision = "m6c09a20261028"
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    registros = conexion.execute(
        sa.text("SELECT id, nombre, apellido FROM personal_institucional")
    ).all()
    for id_, nombre, apellido in registros:
        normal_nombre = nombre.strip().upper()
        normal_apellido = apellido.strip().upper()
        if nombre != normal_nombre or apellido != normal_apellido:
            conexion.execute(
                sa.text(
                    "UPDATE personal_institucional "
                    "SET nombre = :nombre, apellido = :apellido WHERE id = :id"
                ),
                {"nombre": normal_nombre, "apellido": normal_apellido, "id": id_},
            )


def downgrade():
    # Transformación de escritura no reversible: no se puede recuperar
    # la capitalización histórica de forma fiable.
    pass
