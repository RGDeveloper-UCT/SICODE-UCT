# SICODEIAV3 — instrucciones de lectura para Gemini

## Propósito

Gemini funciona únicamente como lector de los documentos escaneados almacenados en Google Drive. No fabrica el archivo final que entra a SICODE. La respuesta de Gemini se entrega a ChatGPT/SICODEIAV3, que la traduce al contrato estricto `sicode.iav3.import.v1`.

## Regla principal

No adivines, no completes por contexto y no conviertas datos a códigos internos de SICODE. Extrae lo que realmente observas en los documentos y conserva la trazabilidad de dónde lo viste.

## Prompt para el lote de prueba de 63 carpetas

Usa este texto en Gemini y selecciona o referencia la carpeta de Google Drive que contiene el lote:

> Revisa COMPLETAMENTE la carpeta `07092026` y todas sus subcarpetas. En este lote existen aproximadamente 63 carpetas documentales. Debes revisar todos los PDF/imágenes de cada carpeta antes de emitir el resultado.
>
> Tu trabajo es LECTURA DOCUMENTAL, no carga a SICODE. No uses códigos internos de SICODE y no fabriques un JSON final de importación. ChatGPT/SICODEIAV3 hará esa traducción después.
>
> OBJETIVO: identificar cada acto administrativo que deba incorporarse al expediente de un SP como anexo y entregar todos los datos observables necesarios para que otro sistema pueda clasificarlo y registrarlo.
>
> REGLAS OBLIGATORIAS:
>
> 1. No deduzcas el No. de SP únicamente del nombre de la carpeta. Debe estar respaldado por el contenido documental. Si el documento no permite confirmarlo, usa `null` y explica la duda.
> 2. Nombres como `ANEXO 74.1` son nombres de carpeta/fuente. No significa SP 74.1 ni número de anexo 74.1.
> 3. No confundas el nombre de la carpeta con el número físico de anexo de File Server. `numero_anexo_documental` solo debe contener un número cuando el propio documento lo indique explícitamente como número de anexo. En cualquier otro caso usa `null`.
> 4. No confundas cantidad de páginas PDF con cantidad de folios. Los folios deben salir de foliación, carátula, sello, oficio o texto documental. Si no se puede determinar, usa `null`.
> 5. Para `fecha_recepcion`, prioriza el sello o constancia de recepción correspondiente al ingreso que se está incorporando. No sustituyas esa fecha por la fecha de elaboración del oficio, acta, informe técnico o formulario.
> 6. Si varios PDF forman un mismo acto administrativo, devuelve UN solo registro y enumera todos los archivos fuente.
> 7. Si una carpeta contiene dos actos distintos que deban individualizarse por separado, devuelve dos registros y explica la separación.
> 8. Distingue documentalmente entre reemplazo, prórroga, reporte de monitoreo, análisis de riesgo, cambio de juzgado, ampliación/cambio de zona, notificación, audiencia, no comunicación, solicitud de comportamiento u otro anexo. Describe el tipo en lenguaje natural; no uses códigos de SICODE.
> 9. En reemplazos identifica por separado cada componente observado: DCT/Smart Tag, correa, cargador cableado, base de cargador y cargador inalámbrico. Si aparecen dos unidades de un mismo componente, conserva la cantidad en `detalle_componentes`.
> 10. No inventes RC, RE, providencia, remitente, folios, fechas, correlativos, números de reporte ni tipo de evento. Si no aparece o no es legible, usa `null`.
> 11. Si un valor es probable pero no seguro, conserva el valor solo si puede leerse y agrégalo a `campos_dudosos` con explicación.
> 12. No incluyas CUI, direcciones personales, teléfonos u otros datos sensibles que SICODE no necesita para este ingreso administrativo.
> 13. Revisa las 63 carpetas y al final informa cuántas carpetas fueron revisadas, cuántos registros documentales detectaste, cuáles quedaron sin acto identificable y cuáles requieren revisión humana.
>
> FORMATO DE SALIDA: responde con UN SOLO JSON válido y nada más. No uses Markdown ni texto antes/después.
>
> Usa esta estructura:
>
> ```json
> {
>   "tipo_salida": "LECTURA_DOCUMENTAL_PARA_SICODEIAV3",
>   "lote_fuente": "07092026",
>   "resumen": {
>     "carpetas_revisadas": 0,
>     "registros_detectados": 0,
>     "carpetas_sin_registro": [],
>     "carpetas_con_dudas": []
>   },
>   "registros": [
>     {
>       "carpeta_fuente": "ANEXO 202",
>       "archivos_fuente": ["202_0001.pdf", "202_0002.pdf"],
>       "sp_observado": "202",
>       "tipo_documental_observado": "Reemplazo de componentes",
>       "numero_anexo_documental": null,
>       "referencia_observada": {
>         "tipo": "RE",
>         "numero_completo": "RE/20251260"
>       },
>       "providencia_observada": "PROVIDENCIA-...",
>       "fecha_recepcion_observada": "2026-09-03",
>       "persona_remite_observada": "Nombre visible en el documento",
>       "folios_observados": "1-15",
>       "componentes_observados": ["DCT", "Correa", "Cargador inalámbrico"],
>       "detalle_componentes": "2 cargadores inalámbricos",
>       "numero_reporte_observado": null,
>       "correlativo_analisis_observado": null,
>       "tipo_evento_observado": null,
>       "es_historico_observado": null,
>       "observaciones_documentales": "Descripción administrativa breve y objetiva.",
>       "campos_dudosos": [],
>       "datos_no_encontrados": [],
>       "evidencias": [
>         {
>           "campo": "fecha_recepcion_observada",
>           "archivo": "202_0008.pdf",
>           "pagina": 1,
>           "referencia_breve": "Sello de recepción visible"
>         }
>       ]
>     }
>   ]
> }
> ```
>
> `evidencias` debe ser breve. No transcribas documentos completos. Su finalidad es indicar dónde verificaste los campos principales.
>
> Antes de responder comprueba internamente que `resumen.carpetas_revisadas` coincide con las carpetas que efectivamente revisaste y que `resumen.registros_detectados` coincide con la longitud de `registros`.

## Qué ocurre después

La respuesta anterior NO se sube a SICODE. Se entrega a ChatGPT/SICODEIAV3. El asistente:

1. revisa coherencia y faltantes;
2. traduce el tipo documental al catálogo oficial de SICODE;
3. normaliza RC/RE, fechas, componentes y metadatos;
4. marca los registros que requieren revisión;
5. fabrica un archivo `.json` con schema `sicode.iav3.import.v1`;
6. declara el número exacto de registros en `control.total_registros`;
7. entrega el archivo al usuario para cargarlo en Administración → SICODEIAV3.

SICODE vuelve a validar el archivo y, cuando corresponde, exige que el administrador confirme el número de anexo contra File Server antes de guardar.
