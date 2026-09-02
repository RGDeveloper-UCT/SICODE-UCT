"""crear metadatos de analisis de riesgo

Revision ID: y6n0i3j8k629
Revises: x5m9h2i7j518
Create Date: 2026-09-02 11:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "y6n0i3j8k629"
down_revision = "x5m9h2i7j518"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analisis_riesgo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("tipo_documento", sa.String(length=80), nullable=True),
        sa.Column("correlativo", sa.String(length=120), nullable=True),
        sa.Column("tipo_evento", sa.String(length=180), nullable=True),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registro_id"),
    )
    op.create_index(
        "ix_analisis_riesgo_correlativo",
        "analisis_riesgo",
        ["correlativo"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_analisis_riesgo_correlativo", table_name="analisis_riesgo")
    op.drop_table("analisis_riesgo")