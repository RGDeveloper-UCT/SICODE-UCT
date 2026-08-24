"""prestamos grupales por rango de sp

Revision ID: r8g3b6c1e952
Revises: q7f2a5b0d841
Create Date: 2026-08-24 14:38:00
"""

from alembic import op
import sqlalchemy as sa


revision = "r8g3b6c1e952"
down_revision = "q7f2a5b0d841"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prestamos_grupos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("numero_control", sa.String(length=100), nullable=False),
        sa.Column("sp_desde", sa.Integer(), nullable=False),
        sa.Column("sp_hasta", sa.Integer(), nullable=False),
        sa.Column("solicitante", sa.String(length=150), nullable=False),
        sa.Column("persona_entrega", sa.String(length=150), nullable=False),
        sa.Column("persona_recibe", sa.String(length=150), nullable=False),
        sa.Column("fecha_prestamo", sa.DateTime(), nullable=False),
        sa.Column("fecha_estimada_devolucion", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sp_desde > 0", name="ck_prestamo_grupo_sp_desde_positivo"),
        sa.CheckConstraint("sp_hasta >= sp_desde", name="ck_prestamo_grupo_rango_valido"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero_control"),
    )
    op.create_index("ix_prestamos_grupos_numero_control", "prestamos_grupos", ["numero_control"], unique=False)
    op.create_index("ix_prestamos_grupos_creado_por_id", "prestamos_grupos", ["creado_por_id"], unique=False)

    op.create_table(
        "prestamos_grupos_detalle",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prestamo_grupo_id", sa.Integer(), nullable=False),
        sa.Column("prestamo_id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("orden > 0", name="ck_prestamo_grupo_detalle_orden_positivo"),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]),
        sa.ForeignKeyConstraint(["prestamo_grupo_id"], ["prestamos_grupos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prestamo_id"], ["prestamos_expedientes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prestamo_grupo_id", "expediente_id", name="uq_prestamo_grupo_expediente"),
        sa.UniqueConstraint("prestamo_id"),
    )
    op.create_index(
        "ix_prestamos_grupos_detalle_prestamo_grupo_id",
        "prestamos_grupos_detalle",
        ["prestamo_grupo_id"],
        unique=False,
    )
    op.create_index(
        "ix_prestamos_grupos_detalle_prestamo_id",
        "prestamos_grupos_detalle",
        ["prestamo_id"],
        unique=False,
    )
    op.create_index(
        "ix_prestamos_grupos_detalle_expediente_id",
        "prestamos_grupos_detalle",
        ["expediente_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_prestamos_grupos_detalle_expediente_id", table_name="prestamos_grupos_detalle")
    op.drop_index("ix_prestamos_grupos_detalle_prestamo_id", table_name="prestamos_grupos_detalle")
    op.drop_index("ix_prestamos_grupos_detalle_prestamo_grupo_id", table_name="prestamos_grupos_detalle")
    op.drop_table("prestamos_grupos_detalle")
    op.drop_index("ix_prestamos_grupos_creado_por_id", table_name="prestamos_grupos")
    op.drop_index("ix_prestamos_grupos_numero_control", table_name="prestamos_grupos")
    op.drop_table("prestamos_grupos")