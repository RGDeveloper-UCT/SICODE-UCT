"""control de accesos al Centro de Control Telematico

Revision ID: v3k7f0g5h396
Revises: u2j6e9f4g285
Create Date: 2026-09-01 10:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "v3k7f0g5h396"
down_revision = "u2j6e9f4g285"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accesos_cct",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=180), nullable=False),
        sa.Column("cui", sa.String(length=13), nullable=False),
        sa.Column("motivo", sa.String(length=40), nullable=False),
        sa.Column("motivo_otro", sa.String(length=240), nullable=True),
        sa.Column("fecha_hora_entrada", sa.DateTime(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accesos_cct_nombre", "accesos_cct", ["nombre"], unique=False)
    op.create_index("ix_accesos_cct_cui", "accesos_cct", ["cui"], unique=False)
    op.create_index("ix_accesos_cct_motivo", "accesos_cct", ["motivo"], unique=False)
    op.create_index("ix_accesos_cct_fecha_hora_entrada", "accesos_cct", ["fecha_hora_entrada"], unique=False)
    op.create_index("ix_accesos_cct_usuario_id", "accesos_cct", ["usuario_id"], unique=False)


def downgrade():
    op.drop_index("ix_accesos_cct_usuario_id", table_name="accesos_cct")
    op.drop_index("ix_accesos_cct_fecha_hora_entrada", table_name="accesos_cct")
    op.drop_index("ix_accesos_cct_motivo", table_name="accesos_cct")
    op.drop_index("ix_accesos_cct_cui", table_name="accesos_cct")
    op.drop_index("ix_accesos_cct_nombre", table_name="accesos_cct")
    op.drop_table("accesos_cct")
