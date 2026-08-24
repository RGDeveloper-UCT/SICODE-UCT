"""diagnostico e ia del analisis documental

Revision ID: q7f2a5b0d841
Revises: p6e1f4a9c730
Create Date: 2026-08-24 13:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "q7f2a5b0d841"
down_revision = "p6e1f4a9c730"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analisis_documentales", sa.Column("calidad_global", sa.Integer(), nullable=True))
    op.add_column("analisis_documentales", sa.Column("pipeline_diagnostico", sa.JSON(), nullable=True))
    op.add_column("analisis_documentales", sa.Column("fuentes_campos", sa.JSON(), nullable=True))
    op.add_column("analisis_documentales", sa.Column("explicaciones_campos", sa.JSON(), nullable=True))
    op.add_column(
        "analisis_documentales",
        sa.Column("ia_utilizada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("analisis_documentales", sa.Column("ia_modelo", sa.String(length=80), nullable=True))
    op.add_column("analisis_documentales", sa.Column("duracion_ms", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("analisis_documentales", "duracion_ms")
    op.drop_column("analisis_documentales", "ia_modelo")
    op.drop_column("analisis_documentales", "ia_utilizada")
    op.drop_column("analisis_documentales", "explicaciones_campos")
    op.drop_column("analisis_documentales", "fuentes_campos")
    op.drop_column("analisis_documentales", "pipeline_diagnostico")
    op.drop_column("analisis_documentales", "calidad_global")
