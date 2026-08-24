"""rectificacion de folios y anexos para prestamos

Revision ID: m4c8e2a7f510
Revises: k9e5f7a3b240
Create Date: 2026-08-24 09:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "m4c8e2a7f510"
down_revision = "k9e5f7a3b240"
branch_labels = None
depends_on = None


def upgrade():
    # Batch mode conserva compatibilidad con SQLite de QA y aplica la misma
    # estructura en PostgreSQL productivo.
    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("folios_rectificados", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("anexos_rectificados", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rectificado_en", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("rectificado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_expedientes_rectificado_por_id_usuarios",
            "usuarios",
            ["rectificado_por_id"],
            ["id"],
        )
        batch_op.create_index(
            op.f("ix_expedientes_rectificado_por_id"),
            ["rectificado_por_id"],
            unique=False,
        )

    op.create_table(
        "anexos_rectificados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=False),
        sa.Column("numero_anexo", sa.String(length=50), nullable=True),
        sa.Column("titulo", sa.String(length=180), nullable=False),
        sa.Column("tipo_anexo", sa.String(length=120), nullable=True),
        sa.Column("fecha_recepcion", sa.Date(), nullable=True),
        sa.Column("persona_entrega", sa.String(length=180), nullable=True),
        sa.Column("rc", sa.String(length=80), nullable=True),
        sa.Column("providencia", sa.String(length=120), nullable=True),
        sa.Column("folios", sa.String(length=80), nullable=True),
        sa.Column("escaneado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fecha_escaneado", sa.Date(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_anexos_rectificados_expediente_id"),
        "anexos_rectificados",
        ["expediente_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_anexos_rectificados_creado_por_id"),
        "anexos_rectificados",
        ["creado_por_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_anexos_rectificados_activo"),
        "anexos_rectificados",
        ["activo"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_anexos_rectificados_activo"), table_name="anexos_rectificados")
    op.drop_index(op.f("ix_anexos_rectificados_creado_por_id"), table_name="anexos_rectificados")
    op.drop_index(op.f("ix_anexos_rectificados_expediente_id"), table_name="anexos_rectificados")
    op.drop_table("anexos_rectificados")

    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_expedientes_rectificado_por_id"))
        batch_op.drop_constraint("fk_expedientes_rectificado_por_id_usuarios", type_="foreignkey")
        batch_op.drop_column("rectificado_por_id")
        batch_op.drop_column("rectificado_en")
        batch_op.drop_column("anexos_rectificados")
        batch_op.drop_column("folios_rectificados")
