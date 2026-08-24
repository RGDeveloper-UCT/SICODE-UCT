# Análisis documental asistido — SICODE-UCT

## Objetivo

Permitir que un usuario autorizado cargue temporalmente un PDF de un anexo u otro documento operativo para que SICODE proponga los metadatos necesarios para los registros existentes de Coordinación.

El módulo no es un repositorio documental. El PDF, las imágenes renderizadas y el texto OCR completo no se guardan en PostgreSQL ni en otra carpeta permanente de SICODE.

## Motor híbrido · Fase 2

La propuesta se construye con varias fuentes independientes:

1. **Texto nativo del PDF**, cuando existe.
2. **OCR local reforzado** para páginas escaneadas: mejora de contraste/nitidez y una segunda configuración de lectura cuando la primera tiene baja calidad.
3. **Reglas determinísticas UCT** para SP, RC, providencia, fecha, anexos, foliación, pagos y monitoreos.
4. **IA local con Ollama**, que interpreta errores típicos de OCR y devuelve únicamente campos JSON de una lista blanca.
5. **Conciliación contra SICODE**, que puede aumentar la confianza si el SP, RC, providencia o anexo propuesto coincide con información ya registrada.
6. **Validación humana obligatoria** antes de crear cualquier registro real.

La IA nunca sustituye una lectura determinística de alta confianza de manera silenciosa. Cuando IA y reglas difieren, el porcentaje del campo baja y se genera una advertencia.

## Porcentajes y calidad

Cada campo puede mostrar:

- porcentaje de confianza;
- fuente de la propuesta (`OCR + reglas`, `IA local`, `SICODE`);
- explicación técnica breve sin reproducir texto sensible del documento.

SICODE calcula también una **calidad global** ponderada según los campos relevantes del tipo de registro. Este valor es un indicador visual de revisión y no constituye una certificación del contenido.

Rangos visuales:

- **90–100%:** confianza alta;
- **70–89%:** revisión recomendada;
- **0–69%:** revisión necesaria.

## Flujo

1. El usuario selecciona un PDF y, opcionalmente, el tipo esperado.
2. SICODE crea un archivo temporal con permisos restringidos, preferentemente en `/dev/shm` cuando está disponible.
3. Se intenta extraer texto nativo con `pypdf`.
4. Las páginas sin texto suficiente se renderizan temporalmente con `pypdfium2` y se procesan mediante Tesseract OCR local.
5. El OCR utiliza preprocesamiento de imagen y puede ejecutar dos modos de segmentación; conserva únicamente métricas técnicas de confianza, nunca imágenes.
6. Las reglas determinísticas generan una primera propuesta.
7. Si está habilitada, Ollama recibe el texto temporal únicamente a través de loopback (`127.0.0.1`) y propone metadatos estructurados.
8. SICODE fusiona reglas e IA y calcula confianza por campo.
9. La propuesta se concilia contra el expediente y registros administrativos existentes sin modificar valores maestros.
10. Antes de devolver el resultado al navegador se elimina el PDF temporal. El texto OCR completo solo existe en memoria durante el análisis.
11. Se crea una propuesta de metadatos en estado `PENDIENTE_VALIDACION`.
12. El usuario revisa y corrige cada campo.
13. Al confirmar, SICODE crea el registro normal de Coordinación y registra la operación en Bitácora.
14. Para anexos, el usuario puede solicitar incorporación al índice documental. SICODE la bloquea si el rango de folios se cruza con un documento activo existente.

## Reglas de seguridad y consistencia

- Solo Administrador y Usuario autorizado pueden analizar y confirmar PDFs. El rol Visor no tiene acceso.
- No se conserva nombre de archivo, PDF, imágenes de páginas ni texto OCR completo.
- La IA documental usa el Ollama local ya instalado; SICODE no envía el contenido a una API externa.
- No se persiste el prompt completo de IA ni evidencia textual del documento.
- El conteo de páginas PDF nunca se interpreta automáticamente como total de folios.
- La rectificación maestra de folios/anexos nunca se modifica automáticamente.
- Las discrepancias se muestran al usuario para revisión humana.
- Un análisis confirmado no puede volver a confirmarse.
- Los archivos temporales abandonados se eliminan por antigüedad al iniciar nuevos análisis.
- El límite de archivo y páginas se controla por configuración.
- Si Ollama no responde, el análisis continúa con OCR + reglas; la indisponibilidad queda visible en el diagnóstico.

## Dependencias

Python:

- `pypdf`
- `pypdfium2`
- `pytesseract`
- `Pillow`

Sistema operativo:

- Tesseract OCR.
- idioma español de Tesseract.

CentOS Stream 10:

```bash
sudo dnf install -y tesseract tesseract-langpack-spa
```

## Configuración opcional

Variables de entorno:

```env
MAX_UPLOAD_MB=45
DOCUMENT_ANALYSIS_MAX_MB=40
DOCUMENT_ANALYSIS_MAX_PAGES=200
DOCUMENT_ANALYSIS_OCR_ENABLED=true
DOCUMENT_ANALYSIS_OCR_LANGUAGE=spa
DOCUMENT_ANALYSIS_TESSERACT_CMD=/usr/bin/tesseract
DOCUMENT_ANALYSIS_OCR_SECOND_PASS=true
DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES=30
DOCUMENT_ANALYSIS_SHOW_DIAGNOSTICS=true

DOCUMENT_ANALYSIS_AI_ENABLED=true
DOCUMENT_ANALYSIS_AI_MODEL=qwen3:1.7b
DOCUMENT_ANALYSIS_AI_TIMEOUT=90
DOCUMENT_ANALYSIS_AI_MAX_CHARS=24000

# Compartidas con la búsqueda IA existente:
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
# DOCUMENT_ANALYSIS_TEMP_DIR=/ruta/temporal/restringida
```

`DOCUMENT_ANALYSIS_AI_MODEL` puede usar el mismo modelo ya descargado para la búsqueda IA. No es obligatorio instalar un modelo distinto para activar la Fase 2.

Si `DOCUMENT_ANALYSIS_TEMP_DIR` no se configura, Linux utiliza `/dev/shm/sicode_document_analysis` cuando es posible; de lo contrario utiliza el directorio temporal del sistema.

## Diagnóstico visual

La interfaz muestra dos tipos de progreso:

- **Durante la espera:** una animación orientativa de las etapas previstas. No pretende ser telemetría en tiempo real.
- **Al finalizar:** la línea de tiempo real almacenada con método de extracción, páginas OCR, confianza OCR media, estado de IA, conciliación SICODE y duración total.

El diagnóstico solo contiene información técnica y porcentajes; no conserva el texto OCR completo.

## Integración futura con HP ScanJet Enterprise Flow N7000 snw1

El motor fue diseñado para que una futura integración con scanner termine alimentando exactamente el mismo flujo. El scanner podrá producir un PDF temporal en una carpeta controlada o mediante un agente local, y SICODE podrá enviarlo al mismo servicio de análisis sin duplicar la lógica de clasificación, extracción, validación y registro.
