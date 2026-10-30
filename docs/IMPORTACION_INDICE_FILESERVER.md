# Integración documental File Server → SICODE-UCT (v1)

## Alcance y autoridad

Esta integración **no conecta directamente** con el recurso compartido de archivos. Recibe
un único libro Excel consolidado con metadatos exportados desde File Server por SP.
No procesa, sube ni conserva documentos sensibles.

Fuentes de SICODE cotejadas:
- `Expediente.no_sp` y `codigo_interno`: identificación del sujeto portador.
- `DocumentoExpediente`: índice vigente, folios generales y folios independientes.
- `AnexoCoordinacion` y `RegistroCoordinacion`: recepción, RC/RE, fecha,
  anexo vinculado y marca `es_vencido`.
- `AnexoRectificado`: antecedentes de rectificación física detallada.
- `Expediente.folios_rectificados` y `anexos_rectificados`: autoridad humana;
  nunca se reescriben por la carga digital.

## Formato del Excel

Nombre de hoja que se importa: **Indice**. Encabezados exactos en fila 1.
Una fila = un documento de un SP; todos los SP en la misma hoja.

```csv
sp,codigo_expediente,seccion,numero_anexo,titulo_anexo,orden,nombre_documento,tipo_documento,folio_inicial,folio_final,estado_revision,fecha_recepcion,rc,providencia,tipo_anexo,es_vencido,observaciones,referencia_file_server
```

Obligatorios siempre: `sp`, `seccion`, `orden`, `nombre_documento`.
`numero_anexo` obligatorio solo si `seccion=ANEXO`, 1–200.
Folios: enteros positivos, inicio ≤ fin; pueden ir ambos vacíos para revisión
manual, pero entonces no se inserta automáticamente el documento.
La `seccion` debe ser PRINCIPAL o ANEXO. En PRINCIPAL, `numero_anexo` vacío.
`es_vencido`: SI, NO o DESCONOCIDO. No convertir ausencia de dato en NO.
`fecha_recepcion`: AAAA-MM-DD. `referencia_file_server` es un código
de metadatos no sensible, NO una ruta confidencial o copia de archivo.

## Estados de la conciliación

| Resultado | Comportamiento |
|---|---|
| NUEVO | Insertar solo el índice documental pendiente de revisión. |
| COINCIDE | Mantener el registro existente, incluso su Verificado y observaciones. |
| DIFERENCIA_INDICE | No actualizar; contrastar nombre y rango en SICODE. |
| DIFERENCIA_ANEXO | No actualizar; rectificar tipo/fecha/RC/vencimiento. |
| ANEXO_AMBIGUO | No vincular automáticamente anexos con identidad dudosa. |
| DUPLICADO_EXCEL | No importar duplicados ni rangos traslapados en el mismo ámbito. |
| SOLO_SICODE | Conservar índice existente ausente en el Excel. |
| REGISTRO_ANULADO | No reactivar automáticamente. |
| SIN_FOLIACION | Revisar físicamente antes de incorporar. |
| SP_NO_EXISTE, CODIGO_DIFERENTE, SIN_EXPEDIENTE_FISICO | No crear SP ni expediente físico automáticamente. |

La foliación de PRINCIPAL es general al expediente; cada ANEXO tiene
foliación independiente que puede empezar en 1.

## Interfaz

En **SP y expedientes**, botón «Importar índice documental masivo».
También existe un acceso desde el índice documental de un SP.
Seleccionar Excel → comparar (solo lectura) → revisar el resumen y el
CSV completo de conciliación → confirmar únicamente los NUEVO.
La vista previa firmada expira a los 30 minutos y se vuelve a cotejar al confirmar.
Si la base cambió, la operación se cancela y exige nueva comparación.

Los documentos nuevos quedan **Pendiente de revisión**, aun cuando el Excel
indique «Verificado». La importación no cambia contadores ni fechas de
rectificación, estado de verificación, datos manuales o anexos vencidos.
Solo puede enlazarse una recepción previamente existente si es unívoca y
existe evidencia concordante (título o RC); nunca se simula una recepción.

## Límites, permisos y auditoría

Máximo: 8 MB comprimidos / 80 MB descomprimidos / 12,000 filas.
Solo usuarios con `puede_modificar`. CSRF obligatorio.
Los cambios se confirman en una sola transacción de BD con auditoría general
y por SP, incluyendo identificadores de fila del Excel y la huella de la
comparación. Importaciones idénticas son idempotentes.

## Pruebas y despliegue

```bash
python -m pytest -q tests/test_importacion_indice_fileserver.py tests/test_importacion_indice_masiva.py
python -m compileall -q app
python -m flask --app run.py db heads
```

Esta actualización no introduce tablas ni migraciones nuevas. Para producción,
respaldar la base, desplegar la rama después de su revisión mediante PR y seguir
`docs/OPERACION_SERVIDOR.md`. No importar de inmediato toda la población:
probar primero un SP de prueba con datos ficticios y confirmar la
conciliación antes de usar datos institucionales.
