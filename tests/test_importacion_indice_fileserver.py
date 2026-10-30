"""Regresión: File Server solo agrega metadatos nuevos sin tocar datos históricos."""
from io import BytesIO
import re
from datetime import date

import pytest
from openpyxl import Workbook
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.documento_expediente import DocumentoExpediente
from app.models.expediente import Expediente
from app.models.usuario import Usuario
from app.services.importacion_indice_fileserver_service import (
    leer_excel, planificar, IndiceFileServerInvalido,
)

HEADERS = ["sp","codigo_expediente","seccion","numero_anexo","titulo_anexo",
           "orden","nombre_documento","tipo_documento","folio_inicial","folio_final",
           "estado_revision","fecha_recepcion","rc","providencia","tipo_anexo",
           "es_vencido","observaciones","referencia_file_server"]


def archivo(filas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Indice"
    ws.append(HEADERS)
    for fila in filas:
        ws.append(fila)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return FileStorage(stream=buffer,filename="file-server.xlsx")


def fila(sp="95", seccion="PRINCIPAL", anexo=None, nombre="Oficio",
         inicio=1, fin=3, **campos):
    dato = dict(zip(HEADERS, [sp,"",seccion,anexo,
        "Monitoreo" if anexo else "",1,nombre,
        "Anexo" if anexo else "Oficio",inicio,fin,
        "Verificado","","","","","DESCONOCIDO","","FS-001"]))
    dato.update(campos)
    return [dato[k] for k in HEADERS]


@pytest.fixture()
def app_fs():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Usuario(
            nombre="Administrador FS",usuario="fs-admin",correo="fs@uct.local",
            password_hash=generate_password_hash("Password123",method="pbkdf2:sha256"),
            debe_cambiar_password=False,rol="administrador",activo=True))
        db.session.add_all([
            Expediente(codigo_interno="UCT-95",no_sp="95",
                       expediente_fisico_registrado=True,activo=True),
            Expediente(codigo_interno="UCT-96",no_sp="96",
                       expediente_fisico_registrado=True,activo=True),
        ])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_lee_varios_sp_y_folios_independientes():
    filas = leer_excel(archivo([
        fila("95",nombre="Principal",inicio=1,fin=3),
        fila("95",seccion="ANEXO",anexo=1,nombre="Informe",inicio=1,fin=3),
        fila("96",nombre="Otro",inicio=1,fin=2),
    ]))
    assert len(filas) == 3
    assert set(item["sp"] for item in filas) == {"95","96"}
    assert filas[1]["numero_anexo"] == 1


def test_rechaza_folio_invertido():
    with pytest.raises(IndiceFileServerInvalido,match="folios"):
        leer_excel(archivo([fila(inicio=7,fin=3)]))


def test_plan_conserva_manual_y_nunca_confirma_verificado(app_fs):
    with app_fs.app_context():
        db.session.add(DocumentoExpediente(
            expediente_id=1,nombre_documento="Oficio",tipo_documento="Oficio",
            folio_inicio=1,folio_fin=3,total_folios=3,
            estado_revision="Verificado",es_anexo=False,activo=True))
        db.session.commit()
        registros = leer_excel(archivo([
            fila(nombre="Oficio"),fila(nombre="Nuevo",inicio=4,fin=5),
            fila(seccion="ANEXO",anexo=1,nombre="Acta",inicio=1,fin=2)
        ]))
        decisiones, resumen = planificar(registros)
        assert [r["estado"] for r in decisiones] == ["COINCIDE","NUEVO","NUEVO"]
        assert resumen["COINCIDE"] == 1
        assert DocumentoExpediente.query.count() == 1
        assert DocumentoExpediente.query.first().estado_revision == "Verificado"


def test_detecta_anexo_vencido_en_desacuerdo(app_fs):
    with app_fs.app_context():
        reg = RegistroCoordinacion(
            tipo="ANEXO",expediente_id=1,no_sp_referencia="95",
            usuario_id=1,fecha_recepcion=date(2026,10,1))
        db.session.add(reg);db.session.flush()
        db.session.add(AnexoCoordinacion(
            registro_id=reg.id,numero_anexo="1",
            titulo="Monitoreo",es_vencido=True))
        db.session.commit()
        registros = leer_excel(archivo([
            fila(seccion="ANEXO",anexo=1,nombre="Reporte",
                 es_vencido="NO")
        ]))
        decisiones, resumen = planificar(registros)
        assert decisiones[0]["estado"] == "DIFERENCIA_ANEXO"
        assert resumen["NUEVO"] == 0


def test_url_importacion_masiva_existe(app_fs):
    reglas = {regla.endpoint:regla.rule for regla in app_fs.url_map.iter_rules()}
    assert reglas["indice_documental.importar_indice_fileserver"] == (
        "/expedientes/indice-documental/importacion-fileserver")


def test_confirmacion_es_idempotente_y_conserva_estado_manual(app_fs):
    with app_fs.app_context():
        db.session.add(DocumentoExpediente(
            expediente_id=1,nombre_documento="Oficio",tipo_documento="Oficio",
            folio_inicio=1,folio_fin=3,total_folios=3,
            estado_revision="Verificado",es_anexo=False,activo=True))
        db.session.commit()
    cliente = app_fs.test_client()
    login = cliente.post("/login",data={"usuario":"fs-admin","password":"Password123"})
    assert login.status_code == 302
    url = "/expedientes/indice-documental/importacion-fileserver"

    def preparar():
        adjunto = archivo([fila(nombre="Oficio"),fila(nombre="Nuevo",inicio=4,fin=5)])
        respuesta = cliente.post(url,data={"accion":"previsualizar",
            "archivo":(adjunto.stream,"indice.xlsx")},content_type="multipart/form-data")
        assert respuesta.status_code == 200
        token = re.search(r'name="token" value="([^"]+)"',respuesta.get_data(as_text=True))
        assert token is not None
        return token.group(1)

    confirmado = cliente.post(url,data={"accion":"confirmar","token":preparar()})
    assert confirmado.status_code == 302
    with app_fs.app_context():
        items = DocumentoExpediente.query.order_by(DocumentoExpediente.id).all()
        assert len(items) == 2
        assert [r.estado_revision for r in items] == [
            "Verificado","Pendiente de revisión"]
    # El mismo Excel puede reimportarse sin duplicar documentos.
    respuesta = cliente.post(url,data={"accion":"confirmar","token":preparar()})
    assert respuesta.status_code == 302
    with app_fs.app_context():
        assert DocumentoExpediente.query.count() == 2


def test_conciliacion_informa_documento_que_solo_existe_en_sicode(app_fs):
    with app_fs.app_context():
        db.session.add(DocumentoExpediente(
            expediente_id=1,nombre_documento="Histórico manual",
            tipo_documento="Documento",folio_inicio=1,folio_fin=1,total_folios=1,
            estado_revision="Verificado",es_anexo=False,activo=True))
        db.session.commit()
        decisiones,resumen = planificar(leer_excel(archivo([
            fila(nombre="Oficio nuevo",inicio=2,fin=3)
        ])))
        assert resumen["SOLO_SICODE"] == 1
        assert any(d["nombre_documento"] == "Histórico manual"
                   and d["estado"] == "SOLO_SICODE" for d in decisiones)
        assert DocumentoExpediente.query.count() == 1
