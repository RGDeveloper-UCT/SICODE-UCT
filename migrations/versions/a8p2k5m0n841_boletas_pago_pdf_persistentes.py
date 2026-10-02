"""boletas de pago PDF persistentes

Revision ID: a8p2k5m0n841
Revises: z7o1j4k9l730
Create Date: 2026-10-02 15:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "a8p2k5m0n841"
down_revision = "z7o1j4k9l730"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "boletas_pago_sp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pago_id", sa.Integer(), nullable=False),
        sa.Column("plantilla_version", sa.String(length=60), nullable=False),
        sa.Column("fecha_comprobante", sa.Date(), nullable=False),
        sa.Column("expediente_numero", sa.String(length=120), nullable=True),
        sa.Column("organo_jurisdiccional", sa.String(length=500), nullable=True),
        sa.Column("nombre_sujeto", sa.String(length=180), nullable=False),
        sa.Column("dias_aplicados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meses_aplicados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tarifa_dia", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tarifa_mes", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("banco_snapshot", sa.String(length=180), nullable=False),
        sa.Column("cuenta_snapshot", sa.String(length=80), nullable=False),
        sa.Column("cuenta_nombre_snapshot", sa.String(length=300), nullable=False),
        sa.Column("elaborado_por_snapshot", sa.String(length=180), nullable=True),
        sa.Column("contacto_snapshot", sa.String(length=220), nullable=True),
        sa.Column("base_legal_snapshot", sa.Text(), nullable=False),
        sa.Column("comprobante_nombre", sa.String(length=255), nullable=False),
        sa.Column("comprobante_mime", sa.String(length=120), nullable=False),
        sa.Column("comprobante_sha256", sa.String(length=64), nullable=False),
        sa.Column("pdf_nombre", sa.String(length=255), nullable=False),
        sa.Column("pdf_mime", sa.String(length=80), nullable=False, server_default="application/pdf"),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("generado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pago_id"], ["pagos_coordinacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pago_id", name="uq_boletas_pago_sp_pago_id"),
    )
    op.create_index(op.f("ix_boletas_pago_sp_pago_id"), "boletas_pago_sp", ["pago_id"], unique=False)
    op.create_index(op.f("ix_boletas_pago_sp_fecha_comprobante"), "boletas_pago_sp", ["fecha_comprobante"], unique=False)
    op.create_index(op.f("ix_boletas_pago_sp_comprobante_sha256"), "boletas_pago_sp", ["comprobante_sha256"], unique=False)
    op.create_index(op.f("ix_boletas_pago_sp_pdf_sha256"), "boletas_pago_sp", ["pdf_sha256"], unique=False)
    op.create_index(op.f("ix_boletas_pago_sp_generado_en"), "boletas_pago_sp", ["generado_en"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_boletas_pago_sp_generado_en"), table_name="boletas_pago_sp")
    op.drop_index(op.f("ix_boletas_pago_sp_pdf_sha256"), table_name="boletas_pago_sp")
    op.drop_index(op.f("ix_boletas_pago_sp_comprobante_sha256"), table_name="boletas_pago_sp")
    op.drop_index(op.f("ix_boletas_pago_sp_fecha_comprobante"), table_name="boletas_pago_sp")
    op.drop_index(op.f("ix_boletas_pago_sp_pago_id"), table_name="boletas_pago_sp")
    op.drop_table("boletas_pago_sp")
