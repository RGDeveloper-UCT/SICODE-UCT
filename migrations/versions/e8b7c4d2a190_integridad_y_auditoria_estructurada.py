"""integridad y auditoria estructurada

Revision ID: e8b7c4d2a190
Revises: d3f1a8b4c902
Create Date: 2026-08-18 13:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "e8b7c4d2a190"
down_revision = "d3f1a8b4c902"
branch_labels = None
depends_on = None


def _assert_sin_inconsistencias(bind):
    rangos_invalidos = bind.execute(sa.text(
        "SELECT COUNT(*) FROM documentos_expediente "
        "WHERE folio_inicio < 1 OR folio_fin < folio_inicio"
    )).scalar()
    if rangos_invalidos:
        raise RuntimeError(
            f"No se puede aplicar la migración: existen {rangos_invalidos} rangos de folios inválidos. "
            "Revise esos registros antes de continuar."
        )

    prestamos_duplicados = bind.execute(sa.text(
        "SELECT COUNT(*) FROM ("
        "SELECT expediente_id FROM prestamos_expedientes "
        "WHERE estado = 'En préstamo' AND activo = true "
        "GROUP BY expediente_id HAVING COUNT(*) > 1"
        ") AS duplicados"
    )).scalar()
    if prestamos_duplicados:
        raise RuntimeError(
            f"No se puede aplicar la migración: {prestamos_duplicados} expediente(s) tienen más de un préstamo activo."
        )

    remisiones_duplicadas = bind.execute(sa.text(
        "SELECT COUNT(*) FROM ("
        "SELECT remision_id, no_sp_referencia FROM remisiones_expedientes "
        "GROUP BY remision_id, no_sp_referencia HAVING COUNT(*) > 1"
        ") AS duplicados"
    )).scalar()
    if remisiones_duplicadas:
        raise RuntimeError(
            f"No se puede aplicar la migración: existen {remisiones_duplicadas} SP repetidos dentro de una misma remisión."
        )


def upgrade():
    bind = op.get_bind()
    _assert_sin_inconsistencias(bind)

    # Corrige únicamente valores derivables antes de activar el constraint.
    bind.execute(sa.text(
        "UPDATE documentos_expediente "
        "SET total_folios = folio_fin - folio_inicio + 1 "
        "WHERE total_folios <> folio_fin - folio_inicio + 1"
    ))

    # El estado de disponibilidad se deriva de préstamos; los antiguos valores
    # usados por ese flujo dejan de ser estado administrativo persistente.
    bind.execute(sa.text(
        "UPDATE expedientes SET estado_administrativo = 'Activo' "
        "WHERE estado_administrativo IN ('En préstamo', 'Devuelto')"
    ))

    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "expediente_fisico_registrado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ))
        batch_op.create_index(
            "ix_expedientes_expediente_fisico_registrado",
            ["expediente_fisico_registrado"],
            unique=False,
        )
        batch_op.create_index("ix_expedientes_no_sp", ["no_sp"], unique=False)

    with op.batch_alter_table("documentos_expediente", schema=None) as batch_op:
        batch_op.create_check_constraint("ck_documento_folio_inicio_positivo", "folio_inicio >= 1")
        batch_op.create_check_constraint("ck_documento_rango_folios", "folio_fin >= folio_inicio")
        batch_op.create_check_constraint(
            "ck_documento_total_folios",
            "total_folios = folio_fin - folio_inicio + 1",
        )
        batch_op.create_index("ix_documentos_expediente_expediente_id", ["expediente_id"], unique=False)
        batch_op.create_index(
            "ix_documento_expediente_folios",
            ["expediente_id", "folio_inicio", "folio_fin"],
            unique=False,
        )
        batch_op.alter_column("es_anexo", existing_type=sa.Boolean(), nullable=False, server_default=sa.false())
        batch_op.alter_column("activo", existing_type=sa.Boolean(), nullable=False, server_default=sa.true())

    with op.batch_alter_table("prestamos_expedientes", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_prestamo_estado",
            "estado IN ('En préstamo', 'Devuelto')",
        )
        batch_op.create_index("ix_prestamos_expedientes_expediente_id", ["expediente_id"], unique=False)
        batch_op.create_index("ix_prestamos_expedientes_estado", ["estado"], unique=False)
        batch_op.alter_column("activo", existing_type=sa.Boolean(), nullable=False, server_default=sa.true())

    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_prestamo_activo_expediente",
            "prestamos_expedientes",
            ["expediente_id"],
            unique=True,
            postgresql_where=sa.text("estado = 'En préstamo' AND activo = true"),
        )
    else:
        op.create_index(
            "uq_prestamo_activo_expediente",
            "prestamos_expedientes",
            ["expediente_id"],
            unique=True,
            sqlite_where=sa.text("estado = 'En préstamo' AND activo = 1"),
        )

    with op.batch_alter_table("anexos_coordinacion", schema=None) as batch_op:
        batch_op.add_column(sa.Column("documento_expediente_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_anexo_coord_documento_expediente",
            "documentos_expediente",
            ["documento_expediente_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_anexo_coord_documento_expediente",
            ["documento_expediente_id"],
        )
        batch_op.create_index(
            "ix_anexos_coordinacion_documento_expediente_id",
            ["documento_expediente_id"],
            unique=False,
        )

    with op.batch_alter_table("remisiones_expedientes", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_remision_sp", ["remision_id", "no_sp_referencia"])

    with op.batch_alter_table("registros_coordinacion", schema=None) as batch_op:
        batch_op.create_index("ix_registros_coordinacion_usuario_id", ["usuario_id"], unique=False)

    with op.batch_alter_table("bitacora", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entidad", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("entidad_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("datos_anteriores", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("datos_posteriores", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("motivo", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(length=255), nullable=True))
        batch_op.alter_column("creado_en", existing_type=sa.DateTime(), nullable=False)
        batch_op.create_index("ix_bitacora_usuario_id", ["usuario_id"], unique=False)
        batch_op.create_index("ix_bitacora_expediente_id", ["expediente_id"], unique=False)
        batch_op.create_index("ix_bitacora_accion", ["accion"], unique=False)
        batch_op.create_index("ix_bitacora_modulo", ["modulo"], unique=False)
        batch_op.create_index("ix_bitacora_entidad", ["entidad"], unique=False)
        batch_op.create_index("ix_bitacora_entidad_id", ["entidad_id"], unique=False)
        batch_op.create_index("ix_bitacora_creado_en", ["creado_en"], unique=False)


def downgrade():
    bind = op.get_bind()

    with op.batch_alter_table("bitacora", schema=None) as batch_op:
        for indice in (
            "ix_bitacora_creado_en",
            "ix_bitacora_entidad_id",
            "ix_bitacora_entidad",
            "ix_bitacora_modulo",
            "ix_bitacora_accion",
            "ix_bitacora_expediente_id",
            "ix_bitacora_usuario_id",
        ):
            batch_op.drop_index(indice)
        batch_op.drop_column("user_agent")
        batch_op.drop_column("motivo")
        batch_op.drop_column("datos_posteriores")
        batch_op.drop_column("datos_anteriores")
        batch_op.drop_column("entidad_id")
        batch_op.drop_column("entidad")

    with op.batch_alter_table("registros_coordinacion", schema=None) as batch_op:
        batch_op.drop_index("ix_registros_coordinacion_usuario_id")

    with op.batch_alter_table("remisiones_expedientes", schema=None) as batch_op:
        batch_op.drop_constraint("uq_remision_sp", type_="unique")

    with op.batch_alter_table("anexos_coordinacion", schema=None) as batch_op:
        batch_op.drop_index("ix_anexos_coordinacion_documento_expediente_id")
        batch_op.drop_constraint("uq_anexo_coord_documento_expediente", type_="unique")
        batch_op.drop_constraint("fk_anexo_coord_documento_expediente", type_="foreignkey")
        batch_op.drop_column("documento_expediente_id")

    op.drop_index("uq_prestamo_activo_expediente", table_name="prestamos_expedientes")
    with op.batch_alter_table("prestamos_expedientes", schema=None) as batch_op:
        batch_op.drop_index("ix_prestamos_expedientes_estado")
        batch_op.drop_index("ix_prestamos_expedientes_expediente_id")
        batch_op.drop_constraint("ck_prestamo_estado", type_="check")

    with op.batch_alter_table("documentos_expediente", schema=None) as batch_op:
        batch_op.drop_index("ix_documento_expediente_folios")
        batch_op.drop_index("ix_documentos_expediente_expediente_id")
        batch_op.drop_constraint("ck_documento_total_folios", type_="check")
        batch_op.drop_constraint("ck_documento_rango_folios", type_="check")
        batch_op.drop_constraint("ck_documento_folio_inicio_positivo", type_="check")

    with op.batch_alter_table("expedientes", schema=None) as batch_op:
        batch_op.drop_index("ix_expedientes_no_sp")
        batch_op.drop_index("ix_expedientes_expediente_fisico_registrado")
        batch_op.drop_column("expediente_fisico_registrado")
