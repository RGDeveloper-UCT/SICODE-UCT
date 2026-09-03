"""crear cola de recepcion documental administrativa

Revision ID: z7o1j4k9l730
Revises: y6n0i3j8k629
Create Date: 2026-09-03 11:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "z7o1j4k9l730"
down_revision = "y6n0i3j8k629"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cola_recepcion_documental",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("correlativo", sa.String(length=32), nullable=False),
        sa.Column("recibido_en", sa.DateTime(), nullable=False),
        sa.Column("recibido_de", sa.String(length=180), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("ubicacion_temporal", sa.String(length=180), nullable=True),
        sa.Column("acciones", sa.JSON(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("completado_en", sa.DateTime(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cola_recepcion_documental_correlativo",
        "cola_recepcion_documental",
        ["correlativo"],
        unique=True,
    )
    op.create_index(
        "ix_cola_recepcion_documental_recibido_en",
        "cola_recepcion_documental",
        ["recibido_en"],
        unique=False,
    )
    op.create_index(
        "ix_cola_recepcion_documental_recibido_de",
        "cola_recepcion_documental",
        ["recibido_de"],
        unique=False,
    )
    op.create_index(
        "ix_cola_recepcion_documental_estado",
        "cola_recepcion_documental",
        ["estado"],
        unique=False,
    )
    op.create_index(
        "ix_cola_recepcion_documental_usuario_id",
        "cola_recepcion_documental",
        ["usuario_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_cola_recepcion_documental_usuario_id", table_name="cola_recepcion_documental")
    op.drop_index("ix_cola_recepcion_documental_estado", table_name="cola_recepcion_documental")
    op.drop_index("ix_cola_recepcion_documental_recibido_de", table_name="cola_recepcion_documental")
    op.drop_index("ix_cola_recepcion_documental_recibido_en", table_name="cola_recepcion_documental")
    op.drop_index("ix_cola_recepcion_documental_correlativo", table_name="cola_recepcion_documental")
    op.drop_table("cola_recepcion_documental")
