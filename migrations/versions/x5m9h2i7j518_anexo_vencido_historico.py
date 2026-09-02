"""marca de anexo vencido o historico

Revision ID: x5m9h2i7j518
Revises: w4l8g1h6i407
Create Date: 2026-09-02 10:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "x5m9h2i7j518"
down_revision = "w4l8g1h6i407"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "anexos_coordinacion",
        sa.Column("es_vencido", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_anexos_coordinacion_es_vencido",
        "anexos_coordinacion",
        ["es_vencido"],
        unique=False,
    )

    # PostgreSQL admite ALTER COLUMN ... DROP DEFAULT de forma directa. SQLite
    # no implementa esa sintaxis y las pruebas de CI crean la base desde cero
    # sobre SQLite. En ese caso Alembic debe recrear la tabla mediante batch.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("anexos_coordinacion") as batch_op:
            batch_op.alter_column(
                "es_vencido",
                existing_type=sa.Boolean(),
                existing_nullable=False,
                server_default=None,
            )
    else:
        op.alter_column(
            "anexos_coordinacion",
            "es_vencido",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade():
    op.drop_index("ix_anexos_coordinacion_es_vencido", table_name="anexos_coordinacion")
    op.drop_column("anexos_coordinacion", "es_vencido")
