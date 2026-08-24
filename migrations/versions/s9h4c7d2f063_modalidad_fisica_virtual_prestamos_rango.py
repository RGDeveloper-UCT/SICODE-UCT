"""modalidad fisica virtual prestamos por rango

Revision ID: s9h4c7d2f063
Revises: r8g3b6c1e952
Create Date: 2026-08-24 15:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "s9h4c7d2f063"
down_revision = "r8g3b6c1e952"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("prestamos_grupos") as batch_op:
        batch_op.add_column(
            sa.Column("modalidad", sa.String(length=20), nullable=False, server_default="FISICO")
        )
        batch_op.add_column(sa.Column("plataforma", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("enlace_virtual", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("asunto_virtual", sa.String(length=250), nullable=True))
        batch_op.create_index("ix_prestamos_grupos_modalidad", ["modalidad"], unique=False)
        batch_op.create_check_constraint(
            "ck_prestamo_grupo_modalidad",
            "modalidad IN ('FISICO', 'VIRTUAL')",
        )
        batch_op.create_check_constraint(
            "ck_prestamo_grupo_datos_modalidad",
            "(modalidad = 'FISICO' AND plataforma IS NULL AND enlace_virtual IS NULL AND asunto_virtual IS NULL) "
            "OR (modalidad = 'VIRTUAL' AND plataforma IS NOT NULL AND enlace_virtual IS NOT NULL AND asunto_virtual IS NOT NULL)",
        )

    with op.batch_alter_table("prestamos_grupos_detalle") as batch_op:
        batch_op.alter_column(
            "prestamo_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(sa.Column("traslado_virtual_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_prestamo_grupo_detalle_traslado_virtual",
            "traslados_virtuales_expediente",
            ["traslado_virtual_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_prestamo_grupo_detalle_traslado_virtual",
            ["traslado_virtual_id"],
        )
        batch_op.create_index(
            "ix_prestamos_grupos_detalle_traslado_virtual_id",
            ["traslado_virtual_id"],
            unique=False,
        )
        batch_op.create_check_constraint(
            "ck_prestamo_grupo_detalle_un_movimiento",
            "(prestamo_id IS NOT NULL AND traslado_virtual_id IS NULL) "
            "OR (prestamo_id IS NULL AND traslado_virtual_id IS NOT NULL)",
        )


def downgrade():
    # Los traslados virtuales individuales permanecen como historial válido.
    # Solo se elimina su asociación grupal para poder restaurar el esquema anterior.
    op.execute("DELETE FROM prestamos_grupos_detalle WHERE traslado_virtual_id IS NOT NULL")
    op.execute("DELETE FROM prestamos_grupos WHERE modalidad = 'VIRTUAL'")

    with op.batch_alter_table("prestamos_grupos_detalle") as batch_op:
        batch_op.drop_constraint("ck_prestamo_grupo_detalle_un_movimiento", type_="check")
        batch_op.drop_index("ix_prestamos_grupos_detalle_traslado_virtual_id")
        batch_op.drop_constraint("uq_prestamo_grupo_detalle_traslado_virtual", type_="unique")
        batch_op.drop_constraint("fk_prestamo_grupo_detalle_traslado_virtual", type_="foreignkey")
        batch_op.drop_column("traslado_virtual_id")
        batch_op.alter_column(
            "prestamo_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    with op.batch_alter_table("prestamos_grupos") as batch_op:
        batch_op.drop_constraint("ck_prestamo_grupo_datos_modalidad", type_="check")
        batch_op.drop_constraint("ck_prestamo_grupo_modalidad", type_="check")
        batch_op.drop_index("ix_prestamos_grupos_modalidad")
        batch_op.drop_column("asunto_virtual")
        batch_op.drop_column("enlace_virtual")
        batch_op.drop_column("plataforma")
        batch_op.drop_column("modalidad")
