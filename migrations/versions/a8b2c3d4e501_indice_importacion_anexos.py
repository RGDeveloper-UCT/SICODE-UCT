"""Campos para importar documentos de cada anexo con folios independientes.

Revision ID: a8b2c3d4e501
Revises: z7o1j4k9l730
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b2c3d4e501"
down_revision = "z7o1j4k9l730"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("documentos_expediente", sa.Column("indice_numero_anexo", sa.Integer(), nullable=True))
    op.add_column("documentos_expediente", sa.Column("indice_titulo_anexo", sa.String(length=180), nullable=True))
    op.add_column("documentos_expediente", sa.Column("indice_orden", sa.Integer(), nullable=True))
    op.create_index("ix_documentos_expediente_indice_numero_anexo", "documentos_expediente", ["indice_numero_anexo"])

def downgrade():
    op.drop_index("ix_documentos_expediente_indice_numero_anexo", table_name="documentos_expediente")
    op.drop_column("documentos_expediente", "indice_orden")
    op.drop_column("documentos_expediente", "indice_titulo_anexo")
    op.drop_column("documentos_expediente", "indice_numero_anexo")
