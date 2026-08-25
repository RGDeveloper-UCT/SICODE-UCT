import re
import shutil
from collections import Counter
from pathlib import Path

from rq import get_current_job

from app import create_app, db
from app.models.analisis_documental import AnalisisDocumental
from app.models.lote_documental import PatronAprendizajeDocumental, SegmentoDocumental
from app.services.bitacora_service import registrar_bitacora
from app.services.coordinacion_service import resolver_expediente
from app.services import lote_documental_service as lote_service
from app.services.pdf_fast_reader import leer_paginas_rapido


def _orientacion(contexto):
    texto = str(contexto or "").strip(); r={"contexto_usuario":texto[:1000]}
    m=re.search(r"\banexo\s*(?:n[úu]mero|no\.?|#)?\s*(\d+)\b",texto,re.I)
    if m:r["numero_anexo"]=m.group(1)
    sps=re.findall(r"\b(?:sp\s*)?(\d{2,4})\b",texto,re.I)
    if sps:r["no_sp"]=sps[-1]
    return r


def _aplicar(datos, o):
    datos=dict(datos or {})
    if o.get("no_sp"):
        _,n=resolver_expediente(o["no_sp"]);datos["no_sp"]=n or o["no_sp"]
    if o.get("numero_anexo"):datos["numero_anexo"]=o["numero_anexo"]
    datos["contexto_usuario"]=o.get("contexto_usuario");return datos


def _pesos():
    return {(p.tipo_documento,p.caracteristica):float(p.peso or 1.0) for p in PatronAprendizajeDocumental.query.all()}


def _crear(resultado,nombre,token,o,usuario_id):
    conteo=Counter(d["tipo"] for d in resultado["documentos"])
    a=AnalisisDocumental(usuario_id=usuario_id,tipo_objetivo="LOTE",tipo_detectado="LOTE_DOCUMENTAL",estado="PENDIENTE_VALIDACION",
        paginas_pdf=resultado["paginas_pdf"],paginas_ocr=resultado["paginas_ocr"],metodo_extraccion="SICODE_IA_ASYNC_FAST",
        datos_detectados={"modo":"SICODE_IA","lote_token":token,"archivo_origen":nombre,"contexto_usuario":o.get("contexto_usuario"),
        "orientacion":o,"documentos_total":resultado["documentos_total"],"tipos_detectados":dict(conteo),"procesamiento_fondo":True,"lector_pdf":"PyMuPDF"},
        confianzas={},discrepancias=[],calidad_global=resultado["calidad_global"],pipeline_diagnostico={"etapas":resultado["pipeline"]},
        fuentes_campos={},explicaciones_campos={},ia_utilizada=resultado["ia_utilizada"],ia_modelo=resultado["ia_modelo"],duracion_ms=resultado["duracion_ms"])
    db.session.add(a);db.session.flush()
    for orden,doc in enumerate(resultado["documentos"],start=1):
        datos=_aplicar(doc["datos"],o);exp,n=resolver_expediente(datos.get("no_sp"))
        if n:datos["no_sp"]=n
        db.session.add(SegmentoDocumental(analisis_id=a.id,expediente_id=exp.id if exp else None,orden=orden,pagina_inicio=doc["pagina_inicio"],
            pagina_fin=doc["pagina_fin"],tipo_detectado=doc["tipo"],estado="PENDIENTE_VALIDACION",calidad_global=doc["calidad_global"],
            datos_detectados=datos,confianzas=doc["confianzas"],fuentes_campos=doc["fuentes_campos"],discrepancias=doc["discrepancias"],
            caracteristicas_clasificacion=doc["caracteristicas"],ia_utilizada=doc["ia_utilizada"],ia_modelo=resultado["ia_modelo"] if doc["ia_utilizada"] else None))
    return a


def _progreso(fase,pct,detalle=None,**extra):
    j=get_current_job()
    if j:
        j.meta.update({"fase":fase,"porcentaje":max(0,min(100,int(pct))),"detalle":detalle or fase,**extra});j.save_meta()


def procesar_lote_sicode_ia(rutas,nombres,contexto,token,usuario_id):
    app=create_app();directorio=Path(rutas[0]).parent if rutas else None;lector_original=lote_service._leer_paginas
    try:
        with app.app_context():
            lote_service._leer_paginas=leer_paginas_rapido;o=_orientacion(contexto);pesos=_pesos();creados=[];fallidos=[];total=max(1,len(rutas))
            _progreso("preparando",2,"Preparando PyMuPDF, OCR paralelo e IA local",usuario_id=usuario_id,lote_token=token)
            for indice,(ruta,nombre) in enumerate(zip(rutas,nombres),start=1):
                _progreso("analizando",max(4,int(((indice-1)/total)*92)),f"Analizando {indice} de {total}: {nombre}",archivo_actual=nombre,
                    archivo_indice=indice,archivos_total=total,usuario_id=usuario_id,lote_token=token)
                try:
                    with open(ruta,"rb") as archivo:
                        r=lote_service.analizar_lote_temporal(archivo,temp_dir=app.config.get("DOCUMENT_ANALYSIS_TEMP_DIR"),max_mb=app.config.get("DOCUMENT_ANALYSIS_MAX_MB",40),
                            max_paginas=app.config.get("DOCUMENT_ANALYSIS_MAX_PAGES",200),ocr_habilitado=app.config.get("DOCUMENT_ANALYSIS_OCR_ENABLED",True),
                            ocr_idioma=app.config.get("DOCUMENT_ANALYSIS_OCR_LANGUAGE","spa"),limpieza_minutos=app.config.get("DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES",30),
                            tesseract_cmd=app.config.get("DOCUMENT_ANALYSIS_TESSERACT_CMD"),ocr_segunda_pasada=app.config.get("DOCUMENT_ANALYSIS_OCR_SECOND_PASS",False),
                            ia_habilitada=app.config.get("DOCUMENT_ANALYSIS_AI_ENABLED",True),ollama_url=app.config.get("OLLAMA_URL","http://127.0.0.1:11434"),
                            ollama_model=app.config.get("SICODE_IA_FAST_MODEL",app.config.get("DOCUMENT_ANALYSIS_AI_MODEL","qwen3:1.7b")),
                            ollama_timeout=app.config.get("DOCUMENT_ANALYSIS_AI_TIMEOUT",180),pesos_aprendidos=pesos)
                    creados.append(_crear(r,nombre,token,o,usuario_id));db.session.commit()
                except Exception as exc:
                    db.session.rollback();app.logger.exception("SICODE.IA background fallo en %s",nombre);fallidos.append(f"{nombre}: {str(exc)[:180]}")
            if not creados:raise RuntimeError("No fue posible analizar ninguno de los PDF del lote.")
            registrar_bitacora(accion="SICODE_IA_ANALISIS_FONDO",modulo="Coordinación",descripcion=f"SICODE.IA finalizó en segundo plano {len(creados)} PDF; {len(fallidos)} con incidencia.",
                usuario_id=usuario_id,entidad="AnalisisDocumental",datos_posteriores={"lote_token":token,"contexto":contexto,"pdf_procesados":len(creados),
                "fallidos":fallidos,"procesamiento_fondo":True,"lector_pdf":"PyMuPDF","ocr_paralelo":True},commit=False);db.session.commit()
            _progreso("terminado",100,"Análisis terminado. Listo para Verificación Humana.",usuario_id=usuario_id,lote_token=token,fallidos=fallidos,revision_lista=True)
            return {"lote_token":token,"procesados":len(creados),"fallidos":fallidos}
    finally:
        lote_service._leer_paginas=lector_original
        if directorio and directorio.exists():shutil.rmtree(directorio,ignore_errors=True)
