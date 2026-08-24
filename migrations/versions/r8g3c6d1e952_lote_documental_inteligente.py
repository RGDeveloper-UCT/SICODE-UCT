"""lote documental inteligente y aprendizaje agregado

Revision ID: r8g3c6d1e952
Revises: q7f2a5b0d841
"""

from alembic import op
import sqlalchemy as sa


revision = "r8g3c6d1e952"
down_revision = "q7f2a5b0d841"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "aprendizaje_documental",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo_documento", sa.String(length=40), nullable=False),
        sa.Column("muestras_confirmadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clasificaciones_correctas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reclasificaciones", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("campos_confirmados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("campos_corregidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nivel_aprendizaje", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tipo_documento", name="uq_aprendizaje_documental_tipo"),
    )
    op.create_index("ix_aprendizaje_documental_tipo_documento", "aprendizaje_documental", ["tipo_documento"])

    op.create_table(
        "patrones_aprendizaje_documental",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo_documento", sa.String(length=40), nullable=False),
        sa.Column("caracteristica", sa.String(length=80), nullable=False),
        sa.Column("aciertos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errores", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("peso", sa.Float(), nullable=False, server_default="1"),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tipo_documento", "caracteristica", name="uq_patron_aprendizaje_tipo_caracteristica"),
    )
    op.create_index("ix_patrones_aprendizaje_documental_tipo_documento", "patrones_aprendizaje_documental", ["tipo_documento"])
    op.create_index("ix_patrones_aprendizaje_documental_caracteristica", "patrones_aprendizaje_documental", ["caracteristica"])

    op.create_table(
        "segmentos_documentales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analisis_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("pagina_inicio", sa.Integer(), nullable=False),
        sa.Column("pagina_fin", sa.Integer(), nullable=False),
        sa.Column("tipo_detectado", sa.String(length=40), nullable=False, server_default="OTRO"),
        sa.Column("tipo_confirmado", sa.String(length=40), nullable=True),
        sa.Column("estado", sa.String(length=30), nullable=False, server_default="PENDIENTE_VALIDACION"),
        sa.Column("calidad_global", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("datos_detectados", sa.JSON(), nullable=False),
        sa.Column("confianzas", sa.JSON(), nullable=False),
        sa.Column("fuentes_campos", sa.JSON(), nullable=False),
        sa.Column("discrepancias", sa.JSON(), nullable=False),
        sa.Column("caracteristicas_clasificacion", sa.JSON(), nullable=False),
        sa.Column("datos_confirmados", sa.JSON(), nullable=True),
        sa.Column("ia_utilizada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ia_modelo", sa.String(length=80), nullable=True),
        sa.Column("registro_id", sa.Integer(), nullable=True),
        sa.Column("documento_expediente_id", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("confirmado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["analisis_id"], ["analisis_documentales.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["documento_expediente_id"], ["documentos_expediente.id"], ondelete="SET NULL"),
        sa.CheckConstraint("pagina_inicio >= 1", name="ck_segmento_pagina_inicio"),
        sa.CheckConstraint("pagina_fin >= pagina_inicio", name="ck_segmento_rango_paginas"),
    )
    op.create_index("ix_segmentos_documentales_analisis_id", "segmentos_documentales", ["analisis_id"])
    op.create_index("ix_segmentos_documentales_tipo_detectado", "segmentos_documentales", ["tipo_detectado"])
    op.create_index("ix_segmentos_documentales_estado", "segmentos_documentales", ["estado"])
    op.create_index("ix_segmentos_documentales_registro_id", "segmentos_documentales", ["registro_id"])
    op.create_index("ix_segmentos_documentales_documento_expediente_id", "segmentos_documentales", ["documento_expediente_id"])


def downgrade():
    op.drop_table("segmentos_documentales")
    op.drop_table("patrones_aprendizaje_documental")
    op.drop_table("aprendizaje_documental")
