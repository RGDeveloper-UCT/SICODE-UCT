"""boletas estructuradas de soporte tecnico

Revision ID: n5d9f3b8c620
Revises: m4c8e2a7f510
Create Date: 2026-08-24 10:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "n5d9f3b8c620"
down_revision = "m4c8e2a7f510"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "servicios_soporte_tecnico",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("numero_boleta", sa.String(length=40), nullable=False),
        sa.Column("fecha_hora_solicitud", sa.DateTime(), nullable=False),
        sa.Column("usuario_solicitante", sa.String(length=180), nullable=False),
        sa.Column("puesto_cargo", sa.String(length=160), nullable=True),
        sa.Column("coordinacion_area", sa.String(length=180), nullable=False),
        sa.Column("tecnico_asignado", sa.String(length=180), nullable=False),
        sa.Column("tipos_servicio", sa.JSON(), nullable=False),
        sa.Column("gestion_usuario_detalles", sa.JSON(), nullable=False),
        sa.Column("hardware_detalles", sa.JSON(), nullable=False),
        sa.Column("software_detalles", sa.JSON(), nullable=False),
        sa.Column("instalacion_detalles", sa.JSON(), nullable=False),
        sa.Column("traslado_detalles", sa.JSON(), nullable=False),
        sa.Column("revision_detalles", sa.JSON(), nullable=False),
        sa.Column("otro_servicio_ti", sa.String(length=220), nullable=True),
        sa.Column("otro_instalacion", sa.String(length=220), nullable=True),
        sa.Column("otro_traslado", sa.String(length=220), nullable=True),
        sa.Column("otro_revision", sa.String(length=220), nullable=True),
        sa.Column("tipo_equipo", sa.String(length=40), nullable=True),
        sa.Column("tipo_equipo_otro", sa.String(length=80), nullable=True),
        sa.Column("marca_modelo", sa.String(length=180), nullable=True),
        sa.Column("numero_serie", sa.String(length=120), nullable=True),
        sa.Column("inventario", sa.String(length=120), nullable=True),
        sa.Column("ip_nombre_equipo", sa.String(length=180), nullable=True),
        sa.Column("descripcion_solicitud", sa.Text(), nullable=False),
        sa.Column("diagnostico_trabajo", sa.Text(), nullable=True),
        sa.Column("estado_final", sa.String(length=30), nullable=False, server_default="PENDIENTE"),
        sa.Column("seguimiento", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fecha_hora_cierre", sa.DateTime(), nullable=True),
        sa.Column("tiempo_empleado", sa.String(length=80), nullable=True),
        sa.Column("observaciones_cierre", sa.Text(), nullable=True),
        sa.Column("nombre_firma_usuario", sa.String(length=180), nullable=True),
        sa.Column("fecha_firma_usuario", sa.Date(), nullable=True),
        sa.Column("nombre_firma_tecnico", sa.String(length=180), nullable=True),
        sa.Column("fecha_firma_tecnico", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("numero_boleta", name="uq_servicios_soporte_numero_boleta"),
        sa.UniqueConstraint("registro_id", name="uq_servicios_soporte_registro_id"),
    )
    for columna in (
        "registro_id",
        "numero_boleta",
        "fecha_hora_solicitud",
        "usuario_solicitante",
        "coordinacion_area",
        "tecnico_asignado",
        "numero_serie",
        "inventario",
        "ip_nombre_equipo",
        "estado_final",
        "seguimiento",
    ):
        op.create_index(
            op.f(f"ix_servicios_soporte_tecnico_{columna}"),
            "servicios_soporte_tecnico",
            [columna],
            unique=False,
        )


def downgrade():
    for columna in reversed((
        "registro_id",
        "numero_boleta",
        "fecha_hora_solicitud",
        "usuario_solicitante",
        "coordinacion_area",
        "tecnico_asignado",
        "numero_serie",
        "inventario",
        "ip_nombre_equipo",
        "estado_final",
        "seguimiento",
    )):
        op.drop_index(op.f(f"ix_servicios_soporte_tecnico_{columna}"), table_name="servicios_soporte_tecnico")
    op.drop_table("servicios_soporte_tecnico")
