"""NEXO 2.0: memoria de propuestas administrativas

Revision ID: a8b9c0d1e2f3
Revises: z7o1j4k9l730
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "z7o1j4k9l730"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "nexo_propuestas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("firma", sa.String(64), nullable=False),
        sa.Column("categoria", sa.String(40), nullable=False),
        sa.Column("modulo", sa.String(70), nullable=False),
        sa.Column("titulo", sa.String(180), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False),
        sa.Column("recomendacion", sa.Text(), nullable=False),
        sa.Column("prioridad", sa.String(12), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("evidencia", sa.JSON(), nullable=False),
        sa.Column("apariciones", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("observado_en", sa.DateTime(), nullable=False),
        sa.Column("revisado_en", sa.DateTime(), nullable=True),
        sa.Column("revisado_por_id", sa.Integer(), nullable=True),
        sa.Column("resultado", sa.String(240), nullable=True),
        sa.ForeignKeyConstraint(["revisado_por_id"], ["usuarios.id"]),
    )
    op.create_index("ix_nexo_propuestas_firma", "nexo_propuestas", ["firma"], unique=True)
    op.create_index("ix_nexo_propuestas_categoria", "nexo_propuestas", ["categoria"])
    op.create_index("ix_nexo_propuestas_estado", "nexo_propuestas", ["estado"])


def downgrade():
    op.drop_index("ix_nexo_propuestas_estado", table_name="nexo_propuestas")
    op.drop_index("ix_nexo_propuestas_categoria", table_name="nexo_propuestas")
    op.drop_index("ix_nexo_propuestas_firma", table_name="nexo_propuestas")
    op.drop_table("nexo_propuestas")
