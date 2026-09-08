import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.analisis_documental import AnalisisDocumental
from app.models.bitacora import Bitacora
from app.models.lote_documental import (
    AprendizajeDocumental,
    PatronAprendizajeDocumental,
    SegmentoDocumental,
)
from app.models.usuario import Usuario
from app.services.cerebro_sicode_absorber import absorber_verificaciones_pendientes


@pytest.fixture()
def app_nexo_absorber():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(
            nombre="QA NEXO",
            usuario="qa-nexo",
            correo="qa-nexo@uct.local",
            password_hash=generate_password_hash("Password123", method="pbkdf2:sha256"),
            debe_cambiar_password=False,
            rol="administrador",
            activo=True,
        )
        db.session.add(usuario)
        db.session.flush()

        analisis = AnalisisDocumental(
            usuario_id=usuario.id,
            tipo_objetivo="LOTE",
            tipo_detectado="LOTE_DOCUMENTAL",
            estado="VALIDACION_PARCIAL",
            paginas_pdf=1,
            paginas_ocr=0,
            metodo_extraccion="SICODE_IA",
            datos_detectados={"modo": "SICODE_IA", "documentos_total": 1},
            confianzas={},
            discrepancias=[],
            ia_utilizada=True,
            ia_modelo="qa-local",
        )
        db.session.add(analisis)
        db.session.flush()

        db.session.add(SegmentoDocumental(
            analisis_id=analisis.id,
            orden=1,
            pagina_inicio=1,
            pagina_fin=1,
            tipo_detectado="ACTA",
            tipo_confirmado="PROVIDENCIA",
            estado="VERIFICADO_HUMANO",
            calidad_global=90,
            datos_detectados={
                "tipo_documento_lote": "ACTA",
                "providencia": "PROV-001",
            },
            datos_confirmados={
                "tipo_documento_lote": "PROVIDENCIA",
                "providencia": "PROV-001",
            },
            confianzas={"tipo_documento_lote": 0.8},
            fuentes_campos={},
            discrepancias=[],
            caracteristicas_clasificacion=["kw_providencia"],
            ia_utilizada=True,
            ia_modelo="qa-local",
        ))
        db.session.commit()
        usuario_id = usuario.id

    yield app, usuario_id

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_absorbe_sicode_ia_y_no_duplica_patrones_nuevos(app_nexo_absorber):
    app, usuario_id = app_nexo_absorber

    with app.app_context():
        aprendidas = absorber_verificaciones_pendientes(usuario_id=usuario_id)
        assert aprendidas == 1

        perfil = AprendizajeDocumental.query.filter_by(tipo_documento="PROVIDENCIA").one()
        assert perfil.muestras_confirmadas == 1
        assert perfil.reclasificaciones == 1

        patron_correcto = PatronAprendizajeDocumental.query.filter_by(
            tipo_documento="PROVIDENCIA",
            caracteristica="kw_providencia",
        ).one()
        assert patron_correcto.aciertos == 1
        assert patron_correcto.errores == 0
        assert patron_correcto.peso == pytest.approx(2.0)

        patron_errado = PatronAprendizajeDocumental.query.filter_by(
            tipo_documento="ACTA",
            caracteristica="kw_providencia",
        ).one()
        assert patron_errado.aciertos == 0
        assert patron_errado.errores == 1
        assert patron_errado.peso == pytest.approx(0.5)

        marca = Bitacora.query.filter_by(
            accion="CEREBRO_SICODE_APRENDIZAJE",
            entidad="SegmentoDocumental",
        ).one()
        assert marca.datos_posteriores["tipo_confirmado"] == "PROVIDENCIA"

        segunda_pasada = absorber_verificaciones_pendientes(usuario_id=usuario_id)
        assert segunda_pasada == 0
        assert AprendizajeDocumental.query.filter_by(tipo_documento="PROVIDENCIA").one().muestras_confirmadas == 1
        assert Bitacora.query.filter_by(
            accion="CEREBRO_SICODE_APRENDIZAJE",
            entidad="SegmentoDocumental",
        ).count() == 1
