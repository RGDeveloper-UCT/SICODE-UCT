"""Control 09: mantenimientos vinculados a activos institucionales.

Revision ID: g1c09m20261021
Revises: f0c091020904
"""
from alembic import op
import sqlalchemy as sa
revision = "g1c09m20261021"
down_revision = "f0c091020904"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "mantenimientos_equipos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipo_id", sa.Integer(), sa.ForeignKey("equipos_institucionales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("boleta_id", sa.Integer(), sa.ForeignKey("servicios_soporte_tecnico.id", ondelete="SET NULL")),
        sa.Column("tecnico_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("diagnostico", sa.Text(), nullable=False),
        sa.Column("trabajo_realizado", sa.Text(), nullable=False),
        sa.Column("estado_final", sa.String(40)),
        sa.Column("requiere_seguimiento", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checklist_version", sa.Integer(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("datos_equipo", sa.JSON(), nullable=False),
        sa.Column("iniciado_en", sa.DateTime()),
        sa.Column("tramo_iniciado_en", sa.DateTime()),
        sa.Column("segundos_acumulados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cerrado_en", sa.DateTime()),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("segundos_acumulados >= 0", name="ck_mantenimiento_segundos"),
        sa.CheckConstraint("tipo IN ('PREVENTIVO','CORRECTIVO','MIXTO')", name="ck_mantenimiento_tipo"),
        sa.CheckConstraint("estado IN ('BORRADOR','EN_PROCESO','PAUSADO','FINALIZADO')", name="ck_mantenimiento_estado"),
    )
    for columna in ("equipo_id", "boleta_id", "estado"):
        op.create_index(f"ix_mantenimientos_equipos_{columna}", "mantenimientos_equipos", [columna])

def downgrade():
    for columna in ("estado", "boleta_id", "equipo_id"):
        op.drop_index(f"ix_mantenimientos_equipos_{columna}", table_name="mantenimientos_equipos")
    op.drop_table("mantenimientos_equipos")
