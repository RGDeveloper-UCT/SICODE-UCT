"""origen documental desde coordinacion

Revision ID: t1i5d8e3f174
Revises: r8g3c6d1e952
Create Date: 2026-08-25 12:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "t1i5d8e3f174"
down_revision = "r8g3c6d1e952"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("documentos_expediente") as batch_op:
        batch_op.add_column(sa.Column("registro_coordinacion_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_documentos_expediente_registro_coordinacion_id",
            ["registro_coordinacion_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_documentos_expediente_registro_coordinacion",
            "registros_coordinacion",
            ["registro_coordinacion_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("documentos_expediente") as batch_op:
        batch_op.drop_constraint(
            "fk_documentos_expediente_registro_coordinacion",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_documentos_expediente_registro_coordinacion_id")
        batch_op.drop_column("registro_coordinacion_id")
