"""Control 09: Personal Institucional, SICOIN/IP y enlace con soporte.

Revision ID: d7c09a210902
Revises: b9c4e7a20109
"""
from alembic import op
import sqlalchemy as sa

revision = "d7c09a210902"
down_revision = "b9c4e7a20109"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "personal_institucional",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("apellido", sa.String(120), nullable=False),
        sa.Column("coordinacion", sa.String(160), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_personal_institucional_coordinacion", "personal_institucional", ["coordinacion"])
    op.add_column("equipos_institucionales", sa.Column("ip_estatica", sa.String(45), nullable=True))
    op.add_column("equipos_institucionales", sa.Column("responsable_personal_id", sa.Integer(), nullable=True))
    op.create_index("ix_equipos_institucionales_ip_estatica", "equipos_institucionales", ["ip_estatica"])
    op.create_index("ix_equipos_institucionales_responsable_personal_id", "equipos_institucionales", ["responsable_personal_id"])
    op.create_foreign_key("fk_equipos_personal", "equipos_institucionales", "personal_institucional", ["responsable_personal_id"], ["id"])
    op.add_column("servicios_soporte_tecnico", sa.Column("equipo_institucional_id", sa.Integer(), nullable=True))
    op.add_column("servicios_soporte_tecnico", sa.Column("personal_institucional_id", sa.Integer(), nullable=True))
    op.create_index("ix_servicios_soporte_tecnico_equipo_institucional_id", "servicios_soporte_tecnico", ["equipo_institucional_id"])
    op.create_index("ix_servicios_soporte_tecnico_personal_institucional_id", "servicios_soporte_tecnico", ["personal_institucional_id"])
    op.create_foreign_key("fk_soporte_equipo", "servicios_soporte_tecnico", "equipos_institucionales", ["equipo_institucional_id"], ["id"])
    op.create_foreign_key("fk_soporte_personal", "servicios_soporte_tecnico", "personal_institucional", ["personal_institucional_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_soporte_personal", "servicios_soporte_tecnico", type_="foreignkey")
    op.drop_constraint("fk_soporte_equipo", "servicios_soporte_tecnico", type_="foreignkey")
    op.drop_index("ix_servicios_soporte_tecnico_personal_institucional_id", table_name="servicios_soporte_tecnico")
    op.drop_index("ix_servicios_soporte_tecnico_equipo_institucional_id", table_name="servicios_soporte_tecnico")
    op.drop_column("servicios_soporte_tecnico", "personal_institucional_id")
    op.drop_column("servicios_soporte_tecnico", "equipo_institucional_id")
    op.drop_constraint("fk_equipos_personal", "equipos_institucionales", type_="foreignkey")
    op.drop_index("ix_equipos_institucionales_responsable_personal_id", table_name="equipos_institucionales")
    op.drop_index("ix_equipos_institucionales_ip_estatica", table_name="equipos_institucionales")
    op.drop_column("equipos_institucionales", "responsable_personal_id")
    op.drop_column("equipos_institucionales", "ip_estatica")
    op.drop_index("ix_personal_institucional_coordinacion", table_name="personal_institucional")
    op.drop_table("personal_institucional")
