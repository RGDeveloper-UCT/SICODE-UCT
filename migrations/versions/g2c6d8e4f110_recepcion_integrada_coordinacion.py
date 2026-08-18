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

    # SQL compatible con PostgreSQL y SQLite de CI. Migra únicamente valores
    # ya existentes y deja intactos los registros que no tenían folios.
    for tabla in ("pagos_coordinacion", "movimientos_dispositivo", "anexos_coordinacion"):
        op.execute(sa.text(
            f"UPDATE registros_coordinacion "
            f"SET folios_recepcion = (SELECT folios FROM {tabla} d WHERE d.registro_id = registros_coordinacion.id) "
            f"WHERE folios_recepcion IS NULL "
            f"AND EXISTS (SELECT 1 FROM {tabla} d WHERE d.registro_id = registros_coordinacion.id AND d.folios IS NOT NULL)"
        ))


def downgrade():
    with op.batch_alter_table("registros_coordinacion", schema=None) as batch_op:
        batch_op.drop_index("ix_registros_coordinacion_persona_entrega")
        batch_op.drop_column("folios_recepcion")
        batch_op.drop_column("persona_entrega")
