"""historial verificaciones

Revision ID: h7a3b5c1d920
Revises: g2c6d8e4f110
Create Date: 2026-08-18 14:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "h7a3b5c1d920"
down_revision = "g2c6d8e4f110"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "verificaciones_expediente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("resultado", sa.String(length=80), nullable=False),
        sa.Column("folios_verificados", sa.Integer(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("origen", sa.String(length=30), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tipo IN ('FISICA', 'DOCUMENTAL', 'INTEGRAL')", name="ck_verificacion_tipo"),
        sa.CheckConstraint(
            "resultado IN ('Verificado', 'Con observaciones', 'Incompleto', 'No localizado')",
            name="ck_verificacion_resultado",
        ),
        sa.CheckConstraint(
            "folios_verificados IS NULL OR folios_verificados >= 0",
            name="ck_verificacion_folios_no_negativos",
        ),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verificaciones_expediente_expediente_id", "verificaciones_expediente", ["expediente_id"], unique=False)
    op.create_index("ix_verificaciones_expediente_usuario_id", "verificaciones_expediente", ["usuario_id"], unique=False)
    op.create_index("ix_verificaciones_expediente_tipo", "verificaciones_expediente", ["tipo"], unique=False)
    op.create_index("ix_verificaciones_expediente_resultado", "verificaciones_expediente", ["resultado"], unique=False)
    op.create_index("ix_verificaciones_expediente_creado_en", "verificaciones_expediente", ["creado_en"], unique=False)


def downgrade():
    op.drop_index("ix_verificaciones_expediente_creado_en", table_name="verificaciones_expediente")
    op.drop_index("ix_verificaciones_expediente_resultado", table_name="verificaciones_expediente")
    op.drop_index("ix_verificaciones_expediente_tipo", table_name="verificaciones_expediente")
    op.drop_index("ix_verificaciones_expediente_usuario_id", table_name="verificaciones_expediente")
    op.drop_index("ix_verificaciones_expediente_expediente_id", table_name="verificaciones_expediente")
    op.drop_table("verificaciones_expediente")
