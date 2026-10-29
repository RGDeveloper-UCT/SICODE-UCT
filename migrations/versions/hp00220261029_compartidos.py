"""HP-002: bóveda institucional compartida (sin tocar registros privados).

Revision ID: hp00220261029
Revises: hp00120261029

Los registros previos permanecen cifrados con la clave del usuario. Su dueño
podrá publicarlos explícitamente después de desbloquearlos con su maestra.
"""
from alembic import op
import sqlalchemy as sa

revision = "hp00220261029"
down_revision = "hp00120261029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hashpass_compartidos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("actualizado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("origen_privado_id", sa.String(36), nullable=True),
        sa.Column("tipo", sa.String(32), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("archivado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("origen_privado_id", name="uq_hp_compartido_origen_privado"),
    )
    op.create_index("ix_hp_compartidos_archivado", "hashpass_compartidos", ["archivado"])


def downgrade():
    total = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM hashpass_compartidos")
    ).scalar()
    if total:
        raise RuntimeError(
            "Downgrade prohibido: existen credenciales institucionales cifradas."
        )
    op.drop_index("ix_hp_compartidos_archivado", table_name="hashpass_compartidos")
    op.drop_table("hashpass_compartidos")
