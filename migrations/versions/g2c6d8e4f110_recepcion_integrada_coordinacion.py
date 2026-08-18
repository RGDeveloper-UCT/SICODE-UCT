"""recepcion integrada coordinacion

Revision ID: g2c6d8e4f110
Revises: f4a1c9e2d730
Create Date: 2026-08-18 14:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "g2c6d8e4f110"
down_revision = "f4a1c9e2d730"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("registros_coordinacion", schema=None) as batch_op:
        batch_op.add_column(sa.Column("persona_entrega", sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column("folios_recepcion", sa.String(length=80), nullable=True))
        batch_op.create_index("ix_registros_coordinacion_persona_entrega", ["persona_entrega"], unique=False)

    # Migra al campo común los folios históricos que ya estaban almacenados en
    # los detalles especializados. Las columnas legacy se conservan por
    # compatibilidad y para permitir rollback sin pérdida.
    op.execute(sa.text(
        "UPDATE registros_coordinacion r SET folios_recepcion = p.folios "
        "FROM pagos_coordinacion p "
        "WHERE p.registro_id = r.id AND r.folios_recepcion IS NULL AND p.folios IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE registros_coordinacion r SET folios_recepcion = m.folios "
        "FROM movimientos_dispositivo m "
        "WHERE m.registro_id = r.id AND r.folios_recepcion IS NULL AND m.folios IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE registros_coordinacion r SET folios_recepcion = a.folios "
        "FROM anexos_coordinacion a "
        "WHERE a.registro_id = r.id AND r.folios_recepcion IS NULL AND a.folios IS NOT NULL"
    ))


def downgrade():
    with op.batch_alter_table("registros_coordinacion", schema=None) as batch_op:
        batch_op.drop_index("ix_registros_coordinacion_persona_entrega")
        batch_op.drop_column("folios_recepcion")
        batch_op.drop_column("persona_entrega")
