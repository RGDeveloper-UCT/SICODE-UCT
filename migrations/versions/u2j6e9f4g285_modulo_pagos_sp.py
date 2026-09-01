"""modulo dedicado de pagos SP

Revision ID: u2j6e9f4g285
Revises: t1i5d8e3f174
Create Date: 2026-09-01 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "u2j6e9f4g285"
down_revision = "t1i5d8e3f174"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pagos_coordinacion") as batch_op:
        batch_op.add_column(sa.Column("banco", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_pagos_coordinacion_banco", ["banco"], unique=False)


def downgrade():
    with op.batch_alter_table("pagos_coordinacion") as batch_op:
        batch_op.drop_index("ix_pagos_coordinacion_banco")
        batch_op.drop_column("banco")
