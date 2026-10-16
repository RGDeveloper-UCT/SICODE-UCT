"""Control 09: activos vinculados a un mismo registro principal.

Revision ID: f0c091020904
Revises: e9c091020903
"""
from alembic import op
import sqlalchemy as sa

revision = "f0c091020904"
down_revision = "e9c091020903"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("equipos_institucionales", sa.Column("equipo_principal_id", sa.Integer(), nullable=True))
    op.create_index("ix_equipos_institucionales_equipo_principal_id", "equipos_institucionales", ["equipo_principal_id"])
    op.create_foreign_key("fk_equipo_principal", "equipos_institucionales", "equipos_institucionales", ["equipo_principal_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_equipo_principal", "equipos_institucionales", type_="foreignkey")
    op.drop_index("ix_equipos_institucionales_equipo_principal_id", table_name="equipos_institucionales")
    op.drop_column("equipos_institucionales", "equipo_principal_id")
