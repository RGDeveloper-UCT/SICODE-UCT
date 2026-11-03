"""Anulación reversible de boletas BSI con motivo y auditoría.

Revision ID: siuct20261103b
Revises: siuct20261103
"""
from alembic import op
import sqlalchemy as sa

revision = "siuct20261103b"
down_revision = "siuct20261103"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("boletas_seguridad_ti", sa.Column("estado_anterior", sa.String(20)))
    op.add_column("boletas_seguridad_ti", sa.Column("anulada_en", sa.DateTime()))
    op.add_column("boletas_seguridad_ti", sa.Column("anulada_por_id", sa.Integer()))
    op.add_column("boletas_seguridad_ti", sa.Column("motivo_anulacion", sa.String(400)))
    op.create_foreign_key(
        "fk_boletas_seguridad_ti_anulada_por", "boletas_seguridad_ti", "usuarios",
        ["anulada_por_id"], ["id"], ondelete="RESTRICT"
    )


def downgrade():
    # Proteger los motivos y la trazabilidad de boletas anuladas.
    conexion = op.get_bind()
    anuladas = conexion.execute(
        sa.text("SELECT COUNT(*) FROM boletas_seguridad_ti WHERE anulada_en IS NOT NULL")
    ).scalar()
    if anuladas:
        raise RuntimeError("No se permite bajar la migración con boletas BSI anuladas.")
    op.drop_constraint("fk_boletas_seguridad_ti_anulada_por", "boletas_seguridad_ti", type_="foreignkey")
    op.drop_column("boletas_seguridad_ti", "motivo_anulacion")
    op.drop_column("boletas_seguridad_ti", "anulada_por_id")
    op.drop_column("boletas_seguridad_ti", "anulada_en")
    op.drop_column("boletas_seguridad_ti", "estado_anterior")
