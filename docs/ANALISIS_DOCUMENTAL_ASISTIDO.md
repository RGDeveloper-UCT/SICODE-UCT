# Análisis documental asistido — SICODE-UCT

## Objetivo

Permitir que un usuario autorizado cargue temporalmente un PDF de un anexo u otro documento operativo para que SICODE proponga los metadatos necesarios para los registros existentes de Coordinación.

El módulo no es un repositorio documental. El PDF, las imágenes renderizadas y el texto OCR completo no se guardan en PostgreSQL ni en otra carpeta permanente de SICODE.

## Flujo

1. El usuario selecciona un PDF y, opcionalmente, el tipo esperado.
2. SICODE crea un archivo temporal con permisos restringidos, preferentemente en `/dev/shm` cuando está disponible.
3. Se intenta extraer texto nativo con `pypdf`.
4. Las páginas sin texto suficiente se renderizan temporalmente con `pypdfium2` y se procesan mediante Tesseract OCR local.
5. El motor aplica una lista blanca y conserva únicamente metadatos administrativos: SP, RC, providencia, fecha, folios, anexo, boleta, total, reporte y campos equivalentes ya utilizados por Coordinación.
6. Antes de devolver el resultado al navegador se elimina el PDF temporal. El texto OCR completo solo existe en memoria durante el análisis.
7. Se crea una propuesta de metadatos en estado `PENDIENTE_VALIDACION`.
8. El usuario revisa y corrige cada campo.
9. Al confirmar, SICODE crea el registro normal de Coordinación y registra la operación en Bitácora.
10. Para anexos, el usuario puede solicitar incorporación al índice documental. SICODE la bloquea si el rango de folios se cruza con un documento activo existente.

## Reglas de seguridad y consistencia

- Solo Administrador y Usuario autorizado pueden analizar y confirmar PDFs. El rol Visor no tiene acceso.
- No se conserva nombre de archivo, PDF, imágenes de páginas ni texto OCR completo.
- El conteo de páginas PDF nunca se interpreta automáticamente como total de folios.
- La rectificación maestra de folios/anexos nunca se modifica automáticamente.
- Las discrepancias se muestran al usuario para revisión humana.
- Un análisis confirmado no puede volver a confirmarse.
- Los archivos temporales abandonados se eliminan por antigüedad al iniciar nuevos análisis.
- El límite de archivo y páginas se controla por configuración.

## Dependencias

Python:

- `pypdf`
- `pypdfium2`
- `pytesseract`
- `Pillow` (ya utilizada por SICODE)

Sistema operativo:

- `tesseract-ocr`
- paquete de idioma español de Tesseract (`tesseract-ocr-spa` en Debian/Ubuntu)

## Configuración opcional

Variables de entorno:

```env
MAX_UPLOAD_MB=45
DOCUMENT_ANALYSIS_MAX_MB=40
DOCUMENT_ANALYSIS_MAX_PAGES=200
DOCUMENT_ANALYSIS_OCR_ENABLED=true
DOCUMENT_ANALYSIS_OCR_LANGUAGE=spa
DOCUMENT_ANALYSIS_TEMP_TTL_MINUTES=30
# DOCUMENT_ANALYSIS_TEMP_DIR=/ruta/temporal/restringida
```

Si `DOCUMENT_ANALYSIS_TEMP_DIR` no se configura, Linux utiliza `/dev/shm/sicode_document_analysis` cuando es posible; de lo contrario utiliza el directorio temporal del sistema.

## Integración futura con HP ScanJet Enterprise Flow N7000 snw1

El motor fue diseñado para que una futura integración con scanner termine alimentando exactamente el mismo flujo. El scanner podrá producir un PDF temporal en una carpeta controlada o mediante un agente local, y SICODE podrá enviarlo al mismo servicio de análisis sin duplicar la lógica de clasificación, extracción, validación y registro.
