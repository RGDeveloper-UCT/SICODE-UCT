"""usuarios online presencia

Revision ID: k9e5f7a3b240
Revises: j8d4e6f2a130
Create Date: 2026-08-20 13:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "k9e5f7a3b240"
down_revision = "j8d4e6f2a130"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "presencias_usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("sesion_id", sa.String(length=64), nullable=False),
        sa.Column("iniciado_en", sa.DateTime(), nullable=False),
        sa.Column("ultimo_pulso_en", sa.DateTime(), nullable=False),
        sa.Column("ruta", sa.String(length=255), nullable=True),
        sa.Column("pagina", sa.String(length=180), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_presencias_usuario_usuario_id"),
        "presencias_usuario",
        ["usuario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_presencias_usuario_sesion_id"),
        "presencias_usuario",
        ["sesion_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_presencias_usuario_ultimo_pulso_en"),
        "presencias_usuario",
        ["ultimo_pulso_en"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_presencias_usuario_ultimo_pulso_en"), table_name="presencias_usuario")
    op.drop_index(op.f("ix_presencias_usuario_sesion_id"), table_name="presencias_usuario")
    op.drop_index(op.f("ix_presencias_usuario_usuario_id"), table_name="presencias_usuario")
    op.drop_table("presencias_usuario")
