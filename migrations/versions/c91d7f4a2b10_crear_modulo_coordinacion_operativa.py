"""Crear modulo de coordinacion operativa

Revision ID: c91d7f4a2b10
Revises: f6d94e964325
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "c91d7f4a2b10"
down_revision = "f6d94e964325"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("registros_coordinacion",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("expediente_id", sa.Integer(), nullable=True), sa.Column("no_sp_referencia", sa.String(50), nullable=True),
        sa.Column("rc", sa.String(80), nullable=True), sa.Column("providencia", sa.String(120), nullable=True),
        sa.Column("fecha_recepcion", sa.Date(), nullable=True), sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("usuario_origen", sa.String(120), nullable=True), sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True), sa.Column("origen_registro", sa.String(30), nullable=False),
        sa.Column("archivo_origen", sa.String(255), nullable=True), sa.Column("lote_importacion", sa.String(64), nullable=True),
        sa.Column("hoja_origen", sa.String(80), nullable=True), sa.Column("fila_origen", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=True), sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]), sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("lote_importacion", "hoja_origen", "fila_origen", name="uq_registro_coord_origen_fila"))
    for nombre, columnas in [
        ("ix_registros_coordinacion_tipo", ["tipo"]), ("ix_registros_coordinacion_expediente_id", ["expediente_id"]),
        ("ix_registros_coordinacion_no_sp_referencia", ["no_sp_referencia"]), ("ix_registros_coordinacion_rc", ["rc"]),
        ("ix_registros_coordinacion_providencia", ["providencia"]), ("ix_registros_coordinacion_fecha_recepcion", ["fecha_recepcion"]),
        ("ix_registros_coordinacion_estado", ["estado"]), ("ix_registros_coordinacion_lote_importacion", ["lote_importacion"]),
        ("ix_registro_coord_tipo_fecha", ["tipo", "fecha_recepcion"])]:
        op.create_index(nombre, "registros_coordinacion", columnas)

    op.create_table("pagos_coordinacion",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("folios", sa.String(80)), sa.Column("periodo_desde", sa.Date()), sa.Column("periodo_hasta", sa.Date()),
        sa.Column("periodo_texto", sa.String(120)), sa.Column("boleta", sa.String(120)), sa.Column("total", sa.Numeric(12, 2)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_table("movimientos_dispositivo",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("movimiento", sa.String(30), nullable=False), sa.Column("descripcion", sa.String(180)), sa.Column("folios", sa.String(80)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_table("anexos_coordinacion",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("tipo_anexo", sa.String(120)), sa.Column("folios", sa.String(80)), sa.Column("escaneado", sa.Boolean(), nullable=False),
        sa.Column("fecha_escaneado", sa.Date()), sa.Column("numero_anexo", sa.String(50)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_table("reportes_monitoreo",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("tipo_documento", sa.String(80)), sa.Column("numero_reporte", sa.String(120)), sa.Column("tipo_evento", sa.String(180)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_table("documentos_emitidos",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("numero_documento", sa.String(120), nullable=False), sa.Column("descripcion", sa.Text()), sa.Column("destino", sa.String(180)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_index("ix_documentos_emitidos_numero_documento", "documentos_emitidos", ["numero_documento"])
    op.create_table("actividades_coordinacion",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("tipo_actividad", sa.String(100)), sa.Column("area_apoyo", sa.String(180)), sa.Column("descripcion", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_index("ix_actividades_coordinacion_tipo_actividad", "actividades_coordinacion", ["tipo_actividad"])
    op.create_table("remisiones_coordinacion",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("destino", sa.String(180), nullable=False), sa.Column("numero_control", sa.String(120)),
        sa.ForeignKeyConstraint(["registro_id"], ["registros_coordinacion.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("registro_id"))
    op.create_index("ix_remisiones_coordinacion_numero_control", "remisiones_coordinacion", ["numero_control"])
    op.create_table("remisiones_expedientes",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("remision_id", sa.Integer(), nullable=False),
        sa.Column("expediente_id", sa.Integer()), sa.Column("no_sp_referencia", sa.String(50), nullable=False),
        sa.Column("folios", sa.String(80)), sa.Column("anexos", sa.String(80)), sa.Column("estado_foliacion", sa.String(80)), sa.Column("observaciones", sa.Text()),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes.id"]), sa.ForeignKeyConstraint(["remision_id"], ["remisiones_coordinacion.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_remisiones_expedientes_remision_id", "remisiones_expedientes", ["remision_id"])
    op.create_index("ix_remisiones_expedientes_expediente_id", "remisiones_expedientes", ["expediente_id"])
    op.create_index("ix_remisiones_expedientes_no_sp_referencia", "remisiones_expedientes", ["no_sp_referencia"])


def downgrade():
    for nombre in ["ix_remisiones_expedientes_no_sp_referencia", "ix_remisiones_expedientes_expediente_id", "ix_remisiones_expedientes_remision_id"]:
        op.drop_index(nombre, table_name="remisiones_expedientes")
    op.drop_table("remisiones_expedientes")
    op.drop_index("ix_remisiones_coordinacion_numero_control", table_name="remisiones_coordinacion"); op.drop_table("remisiones_coordinacion")
    op.drop_index("ix_actividades_coordinacion_tipo_actividad", table_name="actividades_coordinacion"); op.drop_table("actividades_coordinacion")
    op.drop_index("ix_documentos_emitidos_numero_documento", table_name="documentos_emitidos"); op.drop_table("documentos_emitidos")
    op.drop_table("reportes_monitoreo"); op.drop_table("anexos_coordinacion"); op.drop_table("movimientos_dispositivo"); op.drop_table("pagos_coordinacion")
    for nombre in ["ix_registro_coord_tipo_fecha", "ix_registros_coordinacion_lote_importacion", "ix_registros_coordinacion_estado", "ix_registros_coordinacion_fecha_recepcion", "ix_registros_coordinacion_providencia", "ix_registros_coordinacion_rc", "ix_registros_coordinacion_no_sp_referencia", "ix_registros_coordinacion_expediente_id", "ix_registros_coordinacion_tipo"]:
        op.drop_index(nombre, table_name="registros_coordinacion")
    op.drop_table("registros_coordinacion")
