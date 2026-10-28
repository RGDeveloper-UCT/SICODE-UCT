"""Papelera recuperable para tareas y eventos de Agenda UCT.

Revision ID: l5c09a20261028
Revises: k4c09a20261023
"""
from alembic import op
import sqlalchemy as sa

revision = "l5c09a20261028"
down_revision = "k4c09a20261023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agenda_actividades", sa.Column("eliminado_en", sa.DateTime(), nullable=True))
    op.add_column("agenda_actividades", sa.Column("eliminado_por_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("agenda_actividades") as batch:
        batch.create_foreign_key("fk_agenda_actividades_eliminado_por", "usuarios", ["eliminado_por_id"], ["id"])
    op.create_index("ix_agenda_actividades_eliminado_en", "agenda_actividades", ["eliminado_en"])


def downgrade():
    op.drop_index("ix_agenda_actividades_eliminado_en", table_name="agenda_actividades")
    with op.batch_alter_table("agenda_actividades") as batch:
        batch.drop_constraint("fk_agenda_actividades_eliminado_por", type_="foreignkey")
    op.drop_column("agenda_actividades", "eliminado_por_id")
    op.drop_column("agenda_actividades", "eliminado_en")
