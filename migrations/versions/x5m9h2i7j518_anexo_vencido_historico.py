"""marca de anexo vencido o historico

Revision ID: x5m9h2i7j518
Revises: w4l8g1h6i407
Create Date: 2026-09-02 10:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "x5m9h2i7j518"
down_revision = "w4l8g1h6i407"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "anexos_coordinacion",
        sa.Column("es_vencido", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_anexos_coordinacion_es_vencido",
        "anexos_coordinacion",
        ["es_vencido"],
        unique=False,
    )
    op.alter_column("anexos_coordinacion", "es_vencido", server_default=None)


def downgrade():
    op.drop_index("ix_anexos_coordinacion_es_vencido", table_name="anexos_coordinacion")
    op.drop_column("anexos_coordinacion", "es_vencido")
