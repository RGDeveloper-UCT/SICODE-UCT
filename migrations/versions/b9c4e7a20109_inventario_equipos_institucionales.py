"""Control 09: inventario maestro de equipos institucionales.

Revision ID: b9c4e7a20109
Revises: a8b2c3d4e501

No modifica tablas ni datos existentes. Aplicar únicamente tras validar
la revisión activa y realizar un respaldo.
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c4e7a20109"
down_revision = "a8b2c3d4e501"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "equipos_institucionales",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("codigo", sa.String(length=60), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("marca", sa.String(length=100), nullable=True),
        sa.Column("modelo", sa.String(length=120), nullable=True),
        sa.Column("serie", sa.String(length=120), nullable=True),
        sa.Column("numero_inventario", sa.String(length=120), nullable=True),
        sa.Column("area", sa.String(length=160), nullable=True),
        sa.Column("ubicacion", sa.String(length=160), nullable=True),
        sa.Column("responsable_usuario_id", sa.Integer(), nullable=True),
        sa.Column("acceso_institucional", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("tipo_acceso", sa.String(length=40), nullable=False,
                  server_default="INTERNO"),
        sa.Column("estado", sa.String(length=30), nullable=False,
                  server_default="ACTIVO"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["responsable_usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.UniqueConstraint("serie", name="uq_equipos_institucionales_serie"),
        sa.UniqueConstraint("numero_inventario",
                            name="uq_equipos_institucionales_numero_inventario"),
    )
    op.create_index("ix_equipos_institucionales_codigo",
                    "equipos_institucionales", ["codigo"], unique=True)
    op.create_index("ix_equipos_institucionales_responsable_usuario_id",
                    "equipos_institucionales", ["responsable_usuario_id"])
    op.create_index("ix_equipos_institucionales_estado",
                    "equipos_institucionales", ["estado"])


def downgrade():
    # Revertir únicamente en una base de pruebas: elimina el inventario.
    op.drop_index("ix_equipos_institucionales_estado",
                  table_name="equipos_institucionales")
    op.drop_index("ix_equipos_institucionales_responsable_usuario_id",
                  table_name="equipos_institucionales")
    op.drop_index("ix_equipos_institucionales_codigo",
                  table_name="equipos_institucionales")
    op.drop_table("equipos_institucionales")
