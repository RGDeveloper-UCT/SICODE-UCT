"""analisis documental temporal de pdf

Revision ID: p6e1f4a9c730
Revises: n5d9f3b8c620
Create Date: 2026-08-24 12:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "p6e1f4a9c730"
down_revision = "n5d9f3b8c620"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("anexos_coordinacion", sa.Column("titulo", sa.String(length=180), nullable=True))

    op.create_table(
        "analisis_documentales",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=True),
        sa.Column("registro_id", sa.Integer(), nullable=True),
        sa.Column("tipo_objetivo", sa.String(length=30), nullable=False, server_default="AUTO"),
        sa.Column("tipo_detectado", sa.String(length=30), nullable=False, server_default="DOCUMENTO"),
        sa.Column("estado", sa.String(length=30), nullable=False, server_default="PENDIENTE_VALIDACION"),
        sa.Column("paginas_pdf", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paginas_ocr", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metodo_extraccion", sa.String(length=30), nullable=False, server_default="TEXTO_PDF"),
        sa.Column("datos_detectados", sa.JSON(), nullable=False),
        sa.Column("confianzas", sa.JSON(), nullable=False),
        sa.Column("discrepancias", sa.JSON(), nullable=False),
        sa.Column("datos_confirmados", sa.JSON(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("confirmado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registro_id", name="uq_analisis_documentales_registro_id"),
    )
    op.create_index(op.f("ix_analisis_documentales_usuario_id"), "analisis_documentales", ["usuario_id"])
    op.create_index(op.f("ix_analisis_documentales_expediente_id"), "analisis_documentales", ["expediente_id"])
    op.create_index(op.f("ix_analisis_documentales_registro_id"), "analisis_documentales", ["registro_id"])
    op.create_index(op.f("ix_analisis_documentales_estado"), "analisis_documentales", ["estado"])
    op.create_index(op.f("ix_analisis_documentales_creado_en"), "analisis_documentales", ["creado_en"])


def downgrade():
    op.drop_index(op.f("ix_analisis_documentales_creado_en"), table_name="analisis_documentales")
    op.drop_index(op.f("ix_analisis_documentales_estado"), table_name="analisis_documentales")
    op.drop_index(op.f("ix_analisis_documentales_registro_id"), table_name="analisis_documentales")
    op.drop_index(op.f("ix_analisis_documentales_expediente_id"), table_name="analisis_documentales")
    op.drop_index(op.f("ix_analisis_documentales_usuario_id"), table_name="analisis_documentales")
    op.drop_table("analisis_documentales")
    op.drop_column("anexos_coordinacion", "titulo")
