"""ampliar expedientes e importar portadores

Revision ID: d3f1a8b4c902
Revises: c91d7f4a2b10
Create Date: 2026-08-18 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "d3f1a8b4c902"
down_revision = "c91d7f4a2b10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("nombres", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("apellidos", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("genero", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("fecha_nacimiento", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("fecha_instalacion", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("fecha_desinstalacion", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("expediente_oj", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("delito", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("estado_portador", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("juez", sa.String(length=250), nullable=True))
        batch_op.add_column(sa.Column("juzgado_tribunal", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("abogado", sa.String(length=250), nullable=True))
        batch_op.add_column(sa.Column("residencia", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("municipio", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("departamento", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("zona_inclusion", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("zona_exclusion", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("zona_prevencion", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("financiamiento", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("lugar_instalacion", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("estado_monitoreo", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("telefono", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("municipio_residencia", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("departamento_residencia", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("ultima_sincronizacion_portadores", sa.DateTime(), nullable=True))

    op.create_table(
        "importaciones_portadores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("archivo_nombre", sa.String(length=255), nullable=False),
        sa.Column("archivo_hash", sa.String(length=64), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("total_filas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nuevos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actualizados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sin_cambios", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("omitidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vinculados_coordinacion", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_importaciones_portadores_archivo_hash"),
        "importaciones_portadores",
        ["archivo_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_importaciones_portadores_creado_en"),
        "importaciones_portadores",
        ["creado_en"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_importaciones_portadores_creado_en"), table_name="importaciones_portadores")
    op.drop_index(op.f("ix_importaciones_portadores_archivo_hash"), table_name="importaciones_portadores")
    op.drop_table("importaciones_portadores")

    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.drop_column("ultima_sincronizacion_portadores")
        batch_op.drop_column("departamento_residencia")
        batch_op.drop_column("municipio_residencia")
        batch_op.drop_column("telefono")
        batch_op.drop_column("estado_monitoreo")
        batch_op.drop_column("lugar_instalacion")
        batch_op.drop_column("financiamiento")
        batch_op.drop_column("zona_prevencion")
        batch_op.drop_column("zona_exclusion")
        batch_op.drop_column("zona_inclusion")
        batch_op.drop_column("departamento")
        batch_op.drop_column("municipio")
        batch_op.drop_column("residencia")
        batch_op.drop_column("abogado")
        batch_op.drop_column("juzgado_tribunal")
        batch_op.drop_column("juez")
        batch_op.drop_column("estado_portador")
        batch_op.drop_column("delito")
        batch_op.drop_column("expediente_oj")
        batch_op.drop_column("fecha_desinstalacion")
        batch_op.drop_column("fecha_instalacion")
        batch_op.drop_column("fecha_nacimiento")
        batch_op.drop_column("genero")
        batch_op.drop_column("apellidos")
        batch_op.drop_column("nombres")
