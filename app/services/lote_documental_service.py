import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.services.analisis_documental_inteligencia import (
    IAAnalisisNoDisponible,
    ocr_pagina_multipase,
    resolver_tesseract,
)
from app.services.analisis_documental_service import (
    DocumentoInvalido,
    OCRNoDisponible,
    TIPOS_ANEXO,
    extraer_metadatos,
)

TIPOS_DOCUMENTO_LOTE = ("PAGO","PROVIDENCIA","ANEXO","IFT","ACTA","DPI","INSTALACION","DESINSTALACION","MONITOREO","OFICIO","INFORME","RESOLUCION","FORMULARIO","OTRO")
TIPOS_OPERATIVOS = {"PAGO","ANEXO","INSTALACION","DESINSTALACION","MONITOREO"}
CARACTERISTICAS = {"kw_pago":("PAGO","BOLETA","DEPOSITO","COMPROBANTE DE PAGO","TOTAL Q","RECIBO"),"kw_providencia":("PROVIDENCIA",),"kw_anexo":("ANEXO","PRORROGA","AMPLIACION DE ZONA","EXONERACION","MOVILIZACION"),"kw_ift":(" IFT ","INFORME IFT","I.F.T."),"kw_acta":("ACTA","ACTA NUMERO","ACTA NO"),"kw_dpi":("DOCUMENTO PERSONAL DE IDENTIFICACION","RENAP","CODIGO UNICO DE IDENTIFICACION","REPUBLICA DE GUATEMALA"),"kw_instalacion":("INSTALACION","INSTALAR","COLOCACION DE DISPOSITIVO"),"kw_desinstalacion":("DESINSTALACION","DESINSTALAR","RETIRO DE DISPOSITIVO"),"kw_monitoreo":("CENTRO DE CONTROL","MONITOREO","REPORTE DE EVENTO","VICTIM PROXIMITY"),"kw_oficio":("OFICIO",),"kw_informe":("INFORME","INFORME TECNICO"),"kw_resolucion":("RESOLUCION",),"kw_formulario":("FORMULARIO","FORMATO")}
PESO_BASE = {"kw_pago":{"PAGO":4.0},"kw_providencia":{"PROVIDENCIA":5.0},"kw_anexo":{"ANEXO":4.5},"kw_ift":{"IFT":5.0},"kw_acta":{"ACTA":4.8},"kw_dpi":{"DPI":5.0},"kw_instalacion":{"INSTALACION":4.5},"kw_desinstalacion":{"DESINSTALACION":4.8},"kw_monitoreo":{"MONITOREO":4.0},"kw_oficio":{"OFICIO":4.5},"kw_informe":{"INFORME":3.5,"IFT":1.0},"kw_resolucion":{"RESOLUCION":4.8},"kw_formulario":{"FORMULARIO":4.0}}
MARCADORES_INICIO = {"PROVIDENCIA":("PROVIDENCIA",),"ANEXO":("ANEXO",),"ACTA":("ACTA",),"DPI":("DOCUMENTO PERSONAL DE IDENTIFICACION",),"IFT":(" IFT ","I.F.T."),"OFICIO":("OFICIO",),"RESOLUCION":("RESOLUCION",),"FORMULARIO":("FORMULARIO",),"PAGO":("BOLETA","COMPROBANTE DE PAGO","RECIBO")}

def _sin_acentos(valor): return "".join(c for c in unicodedata.normalize("NFKD",str(valor or "")) if not unicodedata.combining(c))
def _normalizar_texto(texto): return re.sub(r"[ \t]+"," ",_sin_acentos(texto).upper().replace("\u00a0"," "))
def _directorio_temporal(configurado=None):
    ruta=Path(configurado) if configurado else (Path("/dev/shm/sicode_document_analysis") if Path("/dev/shm").is_dir() and os.access("/dev/shm",os.W_OK) else Path(tempfile.gettempdir())/"sicode_document_analysis");ruta.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:ruta.chmod(0o700)
    except OSError:pass
    return ruta

def limpiar_temporales(directorio,minutos=30):
    limite=datetime.now()-timedelta(minutes=max(5,int(minutos or 30)))
    for patron in ("sicode_lote_*.pdf","sicode_doc_*.pdf"):
        for ruta in Path(directorio).glob(patron):
            try:
                if datetime.fromtimestamp(ruta.stat().st_mtime)<limite:ruta.unlink(missing_ok=True)
            except OSError:continue

def _leer_paginas(ruta,*,max_paginas=200,ocr_habilitado=True,ocr_idioma="spa",tesseract_cmd=None,ocr_segunda_pasada=False):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:raise RuntimeError("Falta pypdf para separar el lote documental.") from exc
    try:reader=PdfReader(str(ruta),strict=False)
    except PdfReadError as exc:raise DocumentoInvalido("El archivo no es un PDF válido o está dañado.") from exc
    if reader.is_encrypted:
        try:abierto=reader.decrypt("")
        except Exception:abierto=0
        if not abierto:raise DocumentoInvalido("El PDF está protegido con contraseña.")
    total=len(reader.pages)
    if total<1:raise DocumentoInvalido("El PDF no contiene páginas.")
    if total>int(max_paginas):raise DocumentoInvalido(f"El lote contiene {total} páginas y supera el límite de {max_paginas}.")
    paginas=[];pendientes_ocr=[]
    for indice,pagina in enumerate(reader.pages):
        try:texto=pagina.extract_text() or ""
        except Exception:texto=""
        utiles=len(re.sub(r"\W","",texto,flags=re.UNICODE));paginas.append({"pagina":indice+1,"texto":texto,"origen":"TEXTO_PDF","confianza_ocr":None})
        if utiles<45:pendientes_ocr.append(indice)
    paginas_ocr=0
    if pendientes_ocr and ocr_habilitado:
        comando=resolver_tesseract(tesseract_cmd)
        if not comando:
            if all(not p["texto"].strip() for p in paginas):raise OCRNoDisponible("El lote parece escaneado y Tesseract no está disponible.")
        else:
            import pypdfium2 as pdfium
            documento=pdfium.PdfDocument(str(ruta))
            try:
                for indice in pendientes_ocr:
                    pagina_pdf=documento[indice];bitmap=pagina_pdf.render(scale=2.15);imagen=bitmap.to_pil()
                    try:lectura=ocr_pagina_multipase(imagen,idioma=ocr_idioma,tesseract_cmd=comando,segunda_pasada=ocr_segunda_pasada,timeout=55)
                    except IAAnalisisNoDisponible:lectura={"texto":"","confianza":0.0,"modo":"SIN_LECTURA"}
                    finally:
                        try:imagen.close();bitmap.close();pagina_pdf.close()
                        except Exception:pass
                    if (lectura.get("texto") or "").strip():paginas[indice]["texto"]=lectura["texto"];paginas[indice]["origen"]="OCR";paginas[indice]["confianza_ocr"]=int(round(float(lectura.get("confianza") or 0)));paginas_ocr+=1
            finally:documento.close()
    return paginas,paginas_ocr

def _caracteristicas(texto):
    normal=f" {_normalizar_texto(texto)} ";return [clave for clave,terminos in CARACTERISTICAS.items() if any(_normalizar_texto(t) in normal for t in terminos)]
def clasificar_pagina(texto,pesos_aprendidos=None):
    normal=f" {_normalizar_texto(texto)} ";activas=_caracteristicas(texto);puntuacion={t:0.0 for t in TIPOS_DOCUMENTO_LOTE};pesos_aprendidos=pesos_aprendidos or {}
    for c in activas:
        for tipo,base in PESO_BASE.get(c,{}).items():puntuacion[tipo]+=base*max(.45,min(2.25,float(pesos_aprendidos.get((tipo,c),1.0) or 1.0)))
    tipo,puntos=max(puntuacion.items(),key=lambda x:x[1])
    if puntos<=0:tipo,confianza="OTRO",.28
    else:
        segundo=sorted(puntuacion.values(),reverse=True)[1];margen=max(0.0,puntos-segundo);confianza=min(.96,.52+min(puntos,8)*.045+min(margen,5)*.035)
    inicio_fuerte=any(_normalizar_texto(m) in normal[:1800] for m in MARCADORES_INICIO.get(tipo,()))
    return {"tipo":tipo,"confianza":round(confianza,4),"caracteristicas":activas,"inicio_fuerte":inicio_fuerte}

def _ollama_json(url,modelo,payload_usuario,prompt_sistema,timeout):
    req=urllib_request.Request(f"{str(url).rstrip('/')}/api/chat",data=json.dumps({"model":modelo,"messages":[{"role":"system","content":prompt_sistema},{"role":"user","content":payload_usuario}],"stream":False,"format":"json","options":{"temperature":0,"num_ctx":8192}},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")
    try:
        with urllib_request.urlopen(req,timeout=float(timeout)) as respuesta:bruto=json.loads(respuesta.read().decode())
        return json.loads(((bruto.get("message") or {}).get("content") or "").strip())
    except Exception as exc:raise IAAnalisisNoDisponible("La IA local no respondió con JSON válido.") from exc

def _clasificar_paginas_ia(paginas,*,url,modelo,timeout=70,max_chars_pagina=1800):
    resultados={};prompt='Eres el separador documental local de SICODE-UCT. Clasifica cada página en PAGO, PROVIDENCIA, ANEXO, IFT, ACTA, DPI, INSTALACION, DESINSTALACION, MONITOREO, OFICIO, INFORME, RESOLUCION, FORMULARIO, OTRO. Devuelve JSON {"paginas":[{"pagina":1,"tipo":"...","confianza":0.0,"nuevo_documento":false}]}'
    for inicio in range(0,len(paginas),8):
        compacto=[{"pagina":p["pagina"],"texto":str(p.get("texto") or "")[:max_chars_pagina]} for p in paginas[inicio:inicio+8]]
        try:salida=_ollama_json(url,modelo,json.dumps(compacto,ensure_ascii=False),prompt,timeout)
        except IAAnalisisNoDisponible:continue
        for item in salida.get("paginas",[]) if isinstance(salida,dict) else []:
            try:numero=int(item.get("pagina"));tipo=str(item.get("tipo") or "OTRO").upper();conf=max(0,min(.98,float(item.get("confianza") or 0)))
            except:continue
            if tipo not in TIPOS_DOCUMENTO_LOTE:tipo="OTRO"
            resultados[numero]={"tipo":tipo,"confianza":conf,"nuevo_documento":bool(item.get("nuevo_documento"))}
    return resultados

def _fusionar_clasificaciones(paginas,reglas,ia):
    out=[];anterior=None
    for pagina,regla in zip(paginas,reglas):
        dato=ia.get(pagina["pagina"]);tipo=regla["tipo"];conf=regla["confianza"];fuente="Reglas UCT";nuevo=regla["inicio_fuerte"]
        if dato:
            if dato["tipo"]==tipo and tipo!="OTRO":conf=min(.99,max(conf,dato["confianza"])+.05);fuente="Reglas + IA"
            elif dato["confianza"]>=.82 and (conf<.70 or tipo=="OTRO"):tipo=dato["tipo"];conf=min(.90,dato["confianza"]);fuente="IA local"
            nuevo=bool(nuevo or dato.get("nuevo_documento"))
        if anterior is None:nuevo=True
        out.append({**pagina,"tipo":tipo,"confianza_tipo":round(conf,4),"fuente_tipo":fuente,"nuevo_documento":nuevo,"caracteristicas":regla["caracteristicas"]});anterior=tipo
    return out

def _segmentar_paginas(paginas):
    segmentos=[];actual=None
    for pagina in paginas:
        tipo=pagina["tipo"]
        if actual is None:actual={"paginas":[pagina],"tipo":tipo};continue
        if (pagina["nuevo_documento"] and tipo!="OTRO") or (tipo!=actual["tipo"] and tipo!="OTRO" and pagina["confianza_tipo"]>=.72):segmentos.append(actual);actual={"paginas":[pagina],"tipo":tipo}
        else:actual["paginas"].append(pagina)
    if actual:segmentos.append(actual)
    return segmentos

def _numero_documento_generico(texto,tipo):
    etiqueta={"ACTA":"ACTA","IFT":"IFT","OFICIO":"OFICIO","INFORME":"INFORME","RESOLUCION":"RESOLUCION","FORMULARIO":"FORMULARIO"}.get(tipo)
    if not etiqueta:return None
    m=re.findall(rf"\b{etiqueta}\s*(?:NO\.?|NRO\.?|NUMERO|#|:|-)?\s*([A-Z0-9][A-Z0-9./_-]{{1,70}})",_normalizar_texto(texto),flags=re.I);return m[0] if m else None

def _analizar_segmentos_ia(segmentos,*,url,modelo,timeout=70,max_chars_segmento=4500):
    resultados={};prompt='Extrae metadatos administrativos SICODE-UCT. Devuelve JSON {"documentos":[{"indice":1,"tipo":"...","confianza_tipo":0.0,"campos":{}}]}'
    for inicio in range(0,len(segmentos),6):
        bloque=segmentos[inicio:inicio+6];compacto=[]
        for offset,s in enumerate(bloque,start=inicio+1):compacto.append({"indice":offset,"tipo_preliminar":s["tipo"],"texto":"\n".join(p["texto"] for p in s["paginas"])[:max_chars_segmento]})
        try:salida=_ollama_json(url,modelo,json.dumps(compacto,ensure_ascii=False),prompt,timeout)
        except IAAnalisisNoDisponible:continue
        for item in salida.get("documentos",[]) if isinstance(salida,dict) else []:
            try:idx=int(item.get("indice"));tipo=str(item.get("tipo") or "OTRO").upper();conf=max(0,min(.98,float(item.get("confianza_tipo") or 0)))
            except:continue
            resultados[idx]={"tipo":tipo if tipo in TIPOS_DOCUMENTO_LOTE else "OTRO","confianza_tipo":conf,"campos":item.get("campos") or {}}
    return resultados

def _sanitizar_campo(campo,valor):
    if valor in (None,"","null","NULL"):return None
    if campo in {"folio_inicio","folio_fin"}:
        try:return int(str(valor).strip())
        except:return None
    return re.sub(r"\s+"," ",str(valor)).strip()[:180]

def _fusionar_datos_segmento(segmento,indice,ia_segmentos):
    texto="\n".join(p["texto"] for p in segmento["paginas"]);tipo=segmento["tipo"];datos,confianzas,advertencias=extraer_metadatos(texto,len(segmento["paginas"]),tipo_objetivo=tipo if tipo in TIPOS_OPERATIVOS else "AUTO")
    datos.update({"tipo_documento_lote":tipo,"pagina_inicio_pdf":segmento["paginas"][0]["pagina"],"pagina_fin_pdf":segmento["paginas"][-1]["pagina"],"numero_documento":_numero_documento_generico(texto,tipo)})
    if tipo not in TIPOS_OPERATIVOS:datos["tipo_registro"]=None;datos["tipo_documento"]=tipo
    conf_tipo=sum(p["confianza_tipo"] for p in segmento["paginas"])/len(segmento["paginas"]);confianzas["tipo_documento_lote"]=conf_tipo;fuentes={"tipo_documento_lote":list(dict.fromkeys(p["fuente_tipo"] for p in segmento["paginas"]))};discrepancias=list(advertencias);ia=ia_segmentos.get(indice);ia_utilizada=bool(ia)
    if ia and tipo!="DPI":
        for campo,entrada in (ia.get("campos") or {}).items():
            if campo not in {"no_sp","rc","providencia","fecha_recepcion","folio_inicio","folio_fin","numero_anexo","titulo_anexo","tipo_anexo","boleta","total","numero_documento"} or not isinstance(entrada,dict):continue
            valor=_sanitizar_campo(campo,entrada.get("valor"));c=float(entrada.get("confianza") or 0)
            if valor is not None and datos.get(campo) in (None,"") and c>=.58:datos[campo]=valor;confianzas[campo]=min(.84,c*.90);fuentes[campo]=["IA local"]
    inicio=datos.get("folio_inicio");fin=datos.get("folio_fin")
    if inicio and fin and int(fin)>=int(inicio):datos["total_folios"]=int(fin)-int(inicio)+1;datos["folios"]=str(datos["total_folios"])
    relevantes=[v for k,v in confianzas.items() if datos.get(k) not in (None,"") and isinstance(v,(int,float))]+[float(confianzas.get("tipo_documento_lote") or 0)];calidad=max(5,min(99,int(round(sum(relevantes)/max(len(relevantes),1)*100))))
    return {"tipo":tipo,"pagina_inicio":segmento["paginas"][0]["pagina"],"pagina_fin":segmento["paginas"][-1]["pagina"],"datos":datos,"confianzas":confianzas,"fuentes_campos":fuentes,"discrepancias":list(dict.fromkeys(discrepancias)),"caracteristicas":sorted({c for p in segmento["paginas"] for c in p["caracteristicas"]}),"calidad_global":calidad,"ia_utilizada":ia_utilizada}

def analizar_lote_temporal(archivo,*,temp_dir=None,max_mb=40,max_paginas=200,ocr_habilitado=True,ocr_idioma="spa",limpieza_minutos=30,tesseract_cmd=None,ocr_segunda_pasada=False,ia_habilitada=True,ollama_url="http://127.0.0.1:11434",ollama_model="qwen3:1.7b",ollama_timeout=75,pesos_aprendidos=None):
    inicio_total=time.perf_counter();directorio=_directorio_temporal(temp_dir);limpiar_temporales(directorio,limpieza_minutos);descriptor,nombre=tempfile.mkstemp(prefix="sicode_lote_",suffix=".pdf",dir=str(directorio));ruta=Path(nombre)
    try:
        with os.fdopen(descriptor,"wb") as destino:
            origen=getattr(archivo,"stream",archivo)
            if hasattr(origen,"seek"):origen.seek(0)
            shutil.copyfileobj(origen,destino,length=1024*1024)
        if ruta.stat().st_size<5:raise DocumentoInvalido("El PDF está vacío.")
        if ruta.stat().st_size>int(max_mb)*1024*1024:raise DocumentoInvalido(f"El PDF supera el límite de {max_mb} MB.")
        with ruta.open("rb") as lector:
            if lector.read(5)!=b"%PDF-":raise DocumentoInvalido("El archivo no tiene una cabecera PDF válida.")
        paginas,paginas_ocr=_leer_paginas(ruta,max_paginas=max_paginas,ocr_habilitado=ocr_habilitado,ocr_idioma=ocr_idioma,tesseract_cmd=tesseract_cmd,ocr_segunda_pasada=ocr_segunda_pasada)
        reglas=[clasificar_pagina(p["texto"],pesos_aprendidos) for p in paginas];ia_paginas=_clasificar_paginas_ia(paginas,url=ollama_url,modelo=ollama_model,timeout=ollama_timeout) if ia_habilitada else {};fusion=_fusionar_clasificaciones(paginas,reglas,ia_paginas);segmentos=_segmentar_paginas(fusion);ia_segmentos=_analizar_segmentos_ia(segmentos,url=ollama_url,modelo=ollama_model,timeout=ollama_timeout) if ia_habilitada and segmentos else {};documentos=[_fusionar_datos_segmento(s,i,ia_segmentos) for i,s in enumerate(segmentos,start=1)];calidad=int(round(sum(d["calidad_global"] for d in documentos)/max(len(documentos),1)))
        return {"paginas_pdf":len(paginas),"paginas_ocr":paginas_ocr,"documentos":documentos,"documentos_total":len(documentos),"calidad_global":calidad,"ia_utilizada":bool(ia_paginas or ia_segmentos),"ia_modelo":str(ollama_model)[:80] if ia_habilitada else None,"duracion_ms":int((time.perf_counter()-inicio_total)*1000),"pipeline":[{"clave":"paginas","nombre":"Lectura por página","estado":"completada","detalle":f"{len(paginas)} página(s) evaluadas; {paginas_ocr} mediante OCR."},{"clave":"clasificacion","nombre":"Clasificación documental","estado":"completada","detalle":f"{len(documentos)} pieza(s) documentales detectadas."},{"clave":"ia","nombre":"IA local","estado":"completada" if (ia_paginas or ia_segmentos) else "advertencia","detalle":"Ollama apoyó límites, tipo y metadatos." if (ia_paginas or ia_segmentos) else "El lote se resolvió con OCR, reglas y aprendizaje acumulado."},{"clave":"humano","nombre":"Confirmación humana","estado":"pendiente","detalle":"Cada documento debe revisarse antes de crear registros."}]}
    finally:
        try:ruta.unlink(missing_ok=True)
        except OSError:pass
