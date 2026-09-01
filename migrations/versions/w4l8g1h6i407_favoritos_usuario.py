"""favoritos personales por usuario

Revision ID: w4l8g1h6i407
Revises: v3k7f0g5h396
Create Date: 2026-09-01 11:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "w4l8g1h6i407"
down_revision = "v3k7f0g5h396"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "favoritos_usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("icono", sa.String(length=40), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "url", name="uq_favoritos_usuario_usuario_url"),
    )
    op.create_index("ix_favoritos_usuario_usuario_id", "favoritos_usuario", ["usuario_id"], unique=False)


def downgrade():
    op.drop_index("ix_favoritos_usuario_usuario_id", table_name="favoritos_usuario")
    op.drop_table("favoritos_usuario")
