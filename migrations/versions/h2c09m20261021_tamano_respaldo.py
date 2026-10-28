"""Tamaño del respaldo registrado en mantenimiento (MB).

Revision ID: h2c09m20261021
Revises: g1c09m20261021
"""
from alembic import op
import sqlalchemy as sa

revision = "h2c09m20261021"
down_revision = "g1c09m20261021"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("mantenimientos_equipos", sa.Column("respaldo_mb", sa.Numeric(12, 2), nullable=True))
    with op.batch_alter_table("mantenimientos_equipos") as batch:
        batch.create_check_constraint("ck_mantenimiento_respaldo_no_negativo", "respaldo_mb IS NULL OR respaldo_mb >= 0")

def downgrade():
    with op.batch_alter_table("mantenimientos_equipos") as batch:
        batch.drop_constraint("ck_mantenimiento_respaldo_no_negativo", type_="check")
    op.drop_column("mantenimientos_equipos", "respaldo_mb")
