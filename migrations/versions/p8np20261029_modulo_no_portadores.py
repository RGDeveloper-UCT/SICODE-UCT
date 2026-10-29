"""Módulo autónomo NO PORTADORES (NP): datos y relaciones sin SP.

Revision ID: p8np20261029
Revises: n7puct20261028
"""
from alembic import op
import sqlalchemy as sa

revision = "p8np20261029"
down_revision = "n7puct20261028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "no_portadores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("numero_np", sa.String(50), nullable=False),
        sa.Column("codigo_interno", sa.String(50), nullable=False),
        sa.Column("nombre_referencia", sa.String(150)),
        sa.Column("motivo_no_instalacion", sa.Text(), nullable=False),
        sa.Column("fecha_no_instalacion", sa.Date()),
        sa.Column("estado_administrativo", sa.String(80), nullable=False),
        sa.Column("estado_fisico_documental", sa.String(80), nullable=False),
        sa.Column("expediente_fisico_registrado", sa.Boolean(), nullable=False),
        sa.Column("folios_rectificados", sa.Integer()),
        sa.Column("anexos_rectificados", sa.Integer()),
        sa.Column("rectificado_en", sa.DateTime()),
        sa.Column("rectificado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id")),
        sa.Column("nombres", sa.String(150)),
        sa.Column("apellidos", sa.String(150)),
        sa.Column("genero", sa.String(30)),
        sa.Column("fecha_nacimiento", sa.Date()),
        sa.Column("fecha_instalacion", sa.Date()),
        sa.Column("fecha_desinstalacion", sa.Date()),
        sa.Column("expediente_oj", sa.String(120)),
        sa.Column("delito", sa.Text()),
        sa.Column("estado_portador", sa.String(100)),
        sa.Column("juez", sa.String(250)),
        sa.Column("juzgado_tribunal", sa.String(500)),
        sa.Column("abogado", sa.String(250)),
        sa.Column("residencia", sa.Text()),
        sa.Column("municipio", sa.String(150)),
        sa.Column("departamento", sa.String(150)),
        sa.Column("zona_inclusion", sa.Text()),
        sa.Column("zona_exclusion", sa.Text()),
        sa.Column("zona_prevencion", sa.Text()),
        sa.Column("financiamiento", sa.String(150)),
        sa.Column("lugar_instalacion", sa.Text()),
        sa.Column("estado_monitoreo", sa.String(120)),
        sa.Column("telefono", sa.String(80)),
        sa.Column("municipio_residencia", sa.String(150)),
        sa.Column("departamento_residencia", sa.String(150)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("numero_np", name="uq_no_portadores_numero"),
        sa.UniqueConstraint("codigo_interno", name="uq_no_portadores_codigo"),
        sa.CheckConstraint("folios_rectificados IS NULL OR folios_rectificados >= 0", name="ck_np_folios_rectificados"),
        sa.CheckConstraint("anexos_rectificados IS NULL OR anexos_rectificados >= 0", name="ck_np_anexos_rectificados"),
    )
    op.create_index("ix_no_portadores_numero_np", "no_portadores", ["numero_np"])

    op.create_table(
        "ubicaciones_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False, unique=True),
        sa.Column("archivador", sa.String(80)),
        sa.Column("sicoin", sa.String(80)),
        sa.Column("estante", sa.String(80)),
        sa.Column("caja", sa.String(80)),
        sa.Column("modulo", sa.String(80)),
        sa.Column("posicion", sa.String(80)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_en", sa.DateTime()),
        sa.Column("actualizado_en", sa.DateTime()),
    )

    op.create_table(
        "documentos_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("nombre_documento", sa.String(180), nullable=False),
        sa.Column("tipo_documento", sa.String(80), nullable=False),
        sa.Column("folio_inicio", sa.Integer(), nullable=False),
        sa.Column("folio_fin", sa.Integer(), nullable=False),
        sa.Column("total_folios", sa.Integer(), nullable=False),
        sa.Column("estado_revision", sa.String(80), nullable=False),
        sa.Column("es_anexo", sa.Boolean(), nullable=False),
        sa.Column("indice_numero_anexo", sa.Integer()),
        sa.Column("indice_titulo_anexo", sa.String(180)),
        sa.Column("indice_orden", sa.Integer()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("folio_inicio >= 1", name="ck_np_documento_inicio"),
        sa.CheckConstraint("folio_fin >= folio_inicio", name="ck_np_documento_rango"),
        sa.CheckConstraint("total_folios = folio_fin - folio_inicio + 1", name="ck_np_documento_total"),
    )
    op.create_index("ix_documentos_np_np_id", "documentos_np", ["np_id"])
    op.create_index("ix_np_documentos_folios", "documentos_np", ["np_id", "folio_inicio", "folio_fin"])

    op.create_table(
        "anexos_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("numero_anexo", sa.String(50)),
        sa.Column("titulo", sa.String(180), nullable=False),
        sa.Column("tipo_anexo", sa.String(120)),
        sa.Column("fecha_recepcion", sa.Date()),
        sa.Column("persona_entrega", sa.String(180)),
        sa.Column("rc", sa.String(80)),
        sa.Column("providencia", sa.String(120)),
        sa.Column("folios", sa.String(80)),
        sa.Column("escaneado", sa.Boolean(), nullable=False),
        sa.Column("fecha_escaneado", sa.Date()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_anexos_np_np_id", "anexos_np", ["np_id"])

    op.create_table(
        "prestamos_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("numero_control", sa.String(80), nullable=False, unique=True),
        sa.Column("solicitante", sa.String(150), nullable=False),
        sa.Column("persona_entrega", sa.String(150), nullable=False),
        sa.Column("persona_recibe", sa.String(150), nullable=False),
        sa.Column("fecha_prestamo", sa.DateTime(), nullable=False),
        sa.Column("fecha_estimada_devolucion", sa.Date()),
        sa.Column("fecha_real_devolucion", sa.DateTime()),
        sa.Column("persona_devuelve", sa.String(150)),
        sa.Column("persona_recibe_devolucion", sa.String(150)),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("observaciones", sa.Text()),
        sa.Column("observaciones_devolucion", sa.Text()),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("estado IN ('En préstamo','Devuelto')", name="ck_np_prestamo_estado"),
    )
    op.create_index("ix_prestamos_np_np_id", "prestamos_np", ["np_id"])
    op.create_index("uq_np_prestamo_activo", "prestamos_np", ["np_id"], unique=True,
                    postgresql_where=sa.text("estado = 'En préstamo' AND activo = true"),
                    sqlite_where=sa.text("estado = 'En préstamo' AND activo = 1"))

    op.create_table(
        "verificaciones_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("resultado", sa.String(80), nullable=False),
        sa.Column("folios_verificados", sa.Integer()),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tipo IN ('FISICA','DOCUMENTAL','INTEGRAL')", name="ck_np_verificacion_tipo"),
        sa.CheckConstraint("resultado IN ('Verificado','Con observaciones','Incompleto','No localizado')", name="ck_np_verificacion_resultado"),
    )
    op.create_index("ix_verificaciones_np_np_id", "verificaciones_np", ["np_id"])

    op.create_table(
        "alertas_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("tipo_alerta", sa.String(100), nullable=False),
        sa.Column("titulo", sa.String(180), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("gravedad", sa.String(50), nullable=False),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("creada_por_id", sa.Integer(), sa.ForeignKey("usuarios.id")),
        sa.Column("cerrada_por_id", sa.Integer(), sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("cerrado_en", sa.DateTime()),
    )
    op.create_index("ix_alertas_np_np_id", "alertas_np", ["np_id"])

    op.create_table(
        "traslados_virtuales_np",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("np_id", sa.Integer(), sa.ForeignKey("no_portadores.id"), nullable=False),
        sa.Column("numero_constancia", sa.String(80), nullable=False, unique=True),
        sa.Column("destinatario", sa.String(180), nullable=False),
        sa.Column("dependencia_destino", sa.String(220)),
        sa.Column("plataforma", sa.String(80), nullable=False),
        sa.Column("enlace_corto", sa.String(500), nullable=False),
        sa.Column("asunto", sa.String(250), nullable=False),
        sa.Column("observaciones", sa.Text()),
        sa.Column("creado_por_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_traslados_virtuales_np_np_id", "traslados_virtuales_np", ["np_id"])


def downgrade():
    for tabla in ("traslados_virtuales_np", "alertas_np", "verificaciones_np",
                  "prestamos_np", "anexos_np", "documentos_np", "ubicaciones_np", "no_portadores"):
        op.drop_table(tabla)
