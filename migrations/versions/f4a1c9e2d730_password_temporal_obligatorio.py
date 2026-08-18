"""password temporal obligatorio

Revision ID: f4a1c9e2d730
Revises: e8b7c4d2a190
Create Date: 2026-08-18 13:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a1c9e2d730"
down_revision = "e8b7c4d2a190"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "debe_cambiar_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ))
        batch_op.create_index(
            "ix_usuarios_debe_cambiar_password",
            ["debe_cambiar_password"],
            unique=False,
        )

    # La instalación institucional partió de contraseñas temporales comunes.
    # Se exige un cambio individual en el siguiente acceso sin alterar hashes.
    op.execute("UPDATE usuarios SET debe_cambiar_password = true WHERE activo = true")


def downgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_index("ix_usuarios_debe_cambiar_password")
        batch_op.drop_column("debe_cambiar_password")
