"""Modalidad de medidas CERT; conserva la secuencia de boletas BSI.

Revision ID: simpt20261103
Revises: siuct20261103
"""
from alembic import op
import sqlalchemy as sa

revision = "simpt20261103"
down_revision = "siuct20261103"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("boletas_seguridad_ti", sa.Column(
        "tipo_boleta", sa.String(length=20), nullable=False,
        server_default="INTEGRAL"
    ))


def downgrade():
    op.drop_column("boletas_seguridad_ti", "tipo_boleta")
