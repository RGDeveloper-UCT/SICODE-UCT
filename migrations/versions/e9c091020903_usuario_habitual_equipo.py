"""Control 09: distinguir custodio de usuario habitual del equipo.

Revision ID: e9c091020903
Revises: d7c09a210902
"""
from alembic import op
import sqlalchemy as sa

revision = "e9c091020903"
down_revision = "d7c09a210902"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("equipos_institucionales",
        sa.Column("usuario_habitual_personal_id", sa.Integer(), nullable=True))
    op.create_index("ix_equipos_institucionales_usuario_habitual_personal_id",
        "equipos_institucionales", ["usuario_habitual_personal_id"])
    op.create_foreign_key("fk_equipos_usuario_habitual",
        "equipos_institucionales", "personal_institucional",
        ["usuario_habitual_personal_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_equipos_usuario_habitual",
        "equipos_institucionales", type_="foreignkey")
    op.drop_index("ix_equipos_institucionales_usuario_habitual_personal_id",
        table_name="equipos_institucionales")
    op.drop_column("equipos_institucionales", "usuario_habitual_personal_id")
