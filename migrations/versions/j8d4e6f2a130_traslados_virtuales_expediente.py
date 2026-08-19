"""traslados virtuales de expediente

Revision ID: j8d4e6f2a130
Revises: h7a3b5c1d920
Create Date: 2026-08-19 09:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "j8d4e6f2a130"
down_revision = "h7a3b5c1d920"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "traslados_virtuales_expediente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("numero_constancia", sa.String(length=100), nullable=False),
        sa.Column("destinatario", sa.String(length=180), nullable=False),
        sa.Column("dependencia_destino", sa.String(length=220), nullable=True),
        sa.Column("plataforma", sa.String(length=80), nullable=False),
        sa.Column("enlace_corto", sa.String(length=500), nullable=False),
        sa.Column("asunto", sa.String(length=250), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero_constancia"),
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_expediente_id"),
        "traslados_virtuales_expediente",
        ["expediente_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_usuario_id"),
        "traslados_virtuales_expediente",
        ["usuario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_numero_constancia"),
        "traslados_virtuales_expediente",
        ["numero_constancia"],
        unique=True,
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_destinatario"),
        "traslados_virtuales_expediente",
        ["destinatario"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_plataforma"),
        "traslados_virtuales_expediente",
        ["plataforma"],
        unique=False,
    )
    op.create_index(
        op.f("ix_traslados_virtuales_expediente_creado_en"),
        "traslados_virtuales_expediente",
        ["creado_en"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_traslados_virtuales_expediente_creado_en"), table_name="traslados_virtuales_expediente")
    op.drop_index(op.f("ix_traslados_virtuales_expediente_plataforma"), table_name="traslados_virtuales_expediente")
    op.drop_index(op.f("ix_traslados_virtuales_expediente_destinatario"), table_name="traslados_virtuales_expediente")
    op.drop_index(op.f("ix_traslados_virtuales_expediente_numero_constancia"), table_name="traslados_virtuales_expediente")
    op.drop_index(op.f("ix_traslados_virtuales_expediente_usuario_id"), table_name="traslados_virtuales_expediente")
    op.drop_index(op.f("ix_traslados_virtuales_expediente_expediente_id"), table_name="traslados_virtuales_expediente")
    op.drop_table("traslados_virtuales_expediente")
