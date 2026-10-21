"""Respaldo en GB, conservando datos previos almacenados en MB.

Revision ID: j3c09m20261021
Revises: h2c09m20261021
"""
from alembic import op
import sqlalchemy as sa

revision = "j3c09m20261021"
down_revision = "h2c09m20261021"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("mantenimientos_equipos", sa.Column("respaldo_gb", sa.Numeric(12, 2), nullable=True))
    op.execute("UPDATE mantenimientos_equipos SET respaldo_gb = ROUND(respaldo_mb / 1024.0, 2) WHERE respaldo_mb IS NOT NULL")
    # Las validaciones del formulario y del ORM rechazan valores negativos.
    # Se conserva respaldo_mb para compatibilidad y trazabilidad histórica.

def downgrade():
    op.drop_column("mantenimientos_equipos", "respaldo_gb")
