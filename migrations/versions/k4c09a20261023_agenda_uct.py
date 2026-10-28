"""Agenda UCT colaborativa, recordatorios, eventos y cumpleanos

Revision ID: k4c09a20261023
Revises: j3c09m20261021
"""
from alembic import op
import sqlalchemy as sa

revision = "k4c09a20261023"
down_revision = "j3c09m20261021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agenda_actividades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(180), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("tipo", sa.String(24), nullable=False),
        sa.Column("estado", sa.String(24), nullable=False),
        sa.Column("prioridad", sa.String(12), nullable=False),
        sa.Column("visibilidad", sa.String(16), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("padre_id", sa.Integer(), sa.ForeignKey("agenda_actividades.id")),
        sa.Column("inicio", sa.DateTime()),
        sa.Column("vencimiento", sa.DateTime()),
        sa.Column("todo_el_dia", sa.Boolean(), nullable=False),
        sa.Column("lugar", sa.String(180)),
        sa.Column("modalidad", sa.String(24)),
        sa.Column("recurrencia", sa.String(20), nullable=False),
        sa.Column("requiere_revision", sa.Boolean(), nullable=False),
        sa.Column("referencia_sp", sa.String(40)),
        sa.Column("recurrencia_origen_id", sa.Integer(), unique=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("finalizado_en", sa.DateTime()))
    for name in ("tipo", "estado", "prioridad", "creado_por_id", "responsable_id", "padre_id", "vencimiento", "referencia_sp", "recurrencia_origen_id"):
        op.create_index("ix_agenda_actividades_" + name, "agenda_actividades", [name])
    op.create_table("agenda_participantes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actividad_id", sa.Integer(), sa.ForeignKey("agenda_actividades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("respuesta", sa.String(20), nullable=False),
        sa.Column("asignado_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("actividad_id", "usuario_id", name="uq_agenda_participante"))
    op.create_index("ix_agenda_participantes_actividad_id", "agenda_participantes", ["actividad_id"])
    op.create_index("ix_agenda_participantes_usuario_id", "agenda_participantes", ["usuario_id"])
    op.create_table("agenda_comentarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actividad_id", sa.Integer(), sa.ForeignKey("agenda_actividades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False))
    op.create_index("ix_agenda_comentarios_actividad_id", "agenda_comentarios", ["actividad_id"])
    op.create_table("agenda_notificaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("actividad_id", sa.Integer(), sa.ForeignKey("agenda_actividades.id", ondelete="SET NULL")),
        sa.Column("clave", sa.String(180), nullable=False, unique=True),
        sa.Column("titulo", sa.String(180), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("prioridad", sa.String(12), nullable=False),
        sa.Column("obligatoria", sa.Boolean(), nullable=False),
        sa.Column("creada_en", sa.DateTime(), nullable=False),
        sa.Column("leida_en", sa.DateTime()),
        sa.Column("confirmada_en", sa.DateTime()))
    op.create_index("ix_agenda_notificaciones_usuario_id", "agenda_notificaciones", ["usuario_id"])
    op.create_table("agenda_cumpleanos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False, unique=True),
        sa.Column("dia", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table("agenda_cumpleanos")
    op.drop_table("agenda_notificaciones")
    op.drop_table("agenda_comentarios")
    op.drop_table("agenda_participantes")
    op.drop_table("agenda_actividades")
