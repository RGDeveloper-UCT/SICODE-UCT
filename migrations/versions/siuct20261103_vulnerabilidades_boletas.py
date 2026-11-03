"""Seguridad TI: fuentes, CVE y boletas vinculadas al inventario.

Revision ID: siuct20261103
Revises: hp00220261029
"""
from alembic import op
import sqlalchemy as sa

revision = "siuct20261103"
down_revision = "hp00220261029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vulnerabilidades_ti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cve", sa.String(28)),
        sa.Column("fuente", sa.String(24), nullable=False),
        sa.Column("fuentes", sa.JSON(), nullable=False),
        sa.Column("titulo", sa.String(220), nullable=False),
        sa.Column("fabricante", sa.String(140)),
        sa.Column("producto", sa.String(160)),
        sa.Column("severidad", sa.String(16), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("recomendacion", sa.Text(), nullable=False),
        sa.Column("referencia", sa.String(500)),
        sa.Column("fecha_publicacion", sa.Date()),
        sa.Column("fecha_recibido", sa.Date()),
        sa.Column("explotada", sa.Boolean(), nullable=False),
        sa.Column("archivo_pdf", sa.String(80)),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vulnerabilidades_ti_cve", "vulnerabilidades_ti", ["cve"], unique=True)
    op.create_index("ix_vulnerabilidades_ti_fuente", "vulnerabilidades_ti", ["fuente"])
    op.create_index("ix_vulnerabilidades_ti_severidad", "vulnerabilidades_ti", ["severidad"])
    op.create_table(
        "sincronizaciones_vulnerabilidades_ti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente", sa.String(24), nullable=False, unique=True),
        sa.Column("ultimo_intento", sa.DateTime()),
        sa.Column("ultimo_exito", sa.DateTime()),
        sa.Column("ultimo_error", sa.String(400)),
        sa.Column("registros_nuevos", sa.Integer(), nullable=False),
    )
    op.create_table(
        "informes_seguridad_ti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(220), nullable=False),
        sa.Column("emisor", sa.String(160), nullable=False),
        sa.Column("tecnologia", sa.String(40), nullable=False),
        sa.Column("fecha_informe", sa.Date()),
        sa.Column("fecha_recibido", sa.Date()),
        sa.Column("resumen", sa.Text(), nullable=False),
        sa.Column("archivo_nombre", sa.String(80), nullable=False, unique=True),
        sa.Column("nombre_original", sa.String(180), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_informes_seguridad_ti_sha256", "informes_seguridad_ti", ["sha256"], unique=True)
    op.create_table(
        "informe_vulnerabilidad_ti",
        sa.Column("informe_id", sa.Integer(), sa.ForeignKey("informes_seguridad_ti.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("vulnerabilidad_id", sa.Integer(), sa.ForeignKey("vulnerabilidades_ti.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_table(
        "boletas_seguridad_ti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipo_id", sa.Integer(), sa.ForeignKey("equipos_institucionales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tecnico_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("checklist_version", sa.Integer(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("datos_equipo", sa.JSON(), nullable=False),
        sa.Column("versiones", sa.JSON(), nullable=False),
        sa.Column("diagnostico", sa.Text(), nullable=False),
        sa.Column("acciones", sa.Text(), nullable=False),
        sa.Column("resultado_final", sa.String(30)),
        sa.Column("requiere_seguimiento", sa.Boolean(), nullable=False),
        sa.Column("iniciado_en", sa.DateTime()),
        sa.Column("tramo_iniciado_en", sa.DateTime()),
        sa.Column("segundos_acumulados", sa.Integer(), nullable=False),
        sa.Column("cerrado_en", sa.DateTime()),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_boletas_seguridad_ti_equipo_id", "boletas_seguridad_ti", ["equipo_id"])
    op.create_index("ix_boletas_seguridad_ti_estado", "boletas_seguridad_ti", ["estado"])


def downgrade():
    op.drop_table("boletas_seguridad_ti")
    op.drop_table("informe_vulnerabilidad_ti")
    op.drop_index("ix_informes_seguridad_ti_sha256", table_name="informes_seguridad_ti")
    op.drop_table("informes_seguridad_ti")
    op.drop_table("sincronizaciones_vulnerabilidades_ti")
    op.drop_table("vulnerabilidades_ti")
