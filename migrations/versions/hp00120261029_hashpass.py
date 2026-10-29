"""HashPass HP-001: permisos, bóvedas y credenciales cifradas.

Revision ID: hp00120261029
Revises: p8np20261029

IMPORTANTE: requiere aprobación institucional previa al uso de claves reales.
"""
from alembic import op
import sqlalchemy as sa

revision = "hp00120261029"
down_revision = "p8np20261029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hashpass_permisos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autorizado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("autorizado_por", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("usuario_id", name="uq_hashpass_permisos_usuario"),
    )
    op.create_index("ix_hashpass_permisos_usuario_id", "hashpass_permisos", ["usuario_id"], unique=True)

    op.create_table(
        "hashpass_bovedas",
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sal", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("clave_envuelta", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "hashpass_registros",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("archivado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_hashpass_registros_usuario_id", "hashpass_registros", ["usuario_id"])
    op.create_index("ix_hashpass_registros_archivado", "hashpass_registros", ["archivado"])


def downgrade():
    conexion = op.get_bind()
    registros = conexion.execute(sa.text("SELECT count(*) FROM hashpass_registros")).scalar()
    bovedas = conexion.execute(sa.text("SELECT count(*) FROM hashpass_bovedas")).scalar()
    if registros or bovedas:
        raise RuntimeError(
            "Downgrade bloqueado: existen bóvedas o registros cifrados. "
            "Nunca destruya secretos mediante downgrade; use una estrategia de respaldo/migración aprobada."
        )
    op.drop_index("ix_hashpass_registros_archivado", table_name="hashpass_registros")
    op.drop_index("ix_hashpass_registros_usuario_id", table_name="hashpass_registros")
    op.drop_table("hashpass_registros")
    op.drop_table("hashpass_bovedas")
    op.drop_index("ix_hashpass_permisos_usuario_id", table_name="hashpass_permisos")
    op.drop_table("hashpass_permisos")
