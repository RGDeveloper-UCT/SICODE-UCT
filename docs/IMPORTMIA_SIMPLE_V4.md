# ImportM.IA v4 — recepción simple de documentos de ChatGPT Work

## Contrato
El Excel contiene `INSTRUCCIONES` (solo Work) y cuatro hojas operativas:
`EXPEDIENTES`, `Indice`, `ANEXOS`, `PAGOS`.
Encabezados oficiales definidos en `app/services/importmia_simple_service.py` (`HEADERS`).
La hoja `Indice` conserva los 18 campos de SICODE File Server.

## Comportamiento
- EXPEDIENTES: solo comparación del campo físico. El Excel **jamás** cambia
  `expediente_fisico_registrado`, por lo que el indicador rojo de «sin físico»
  permanece hasta recepción física institucional.
- Indice: usa el motor `planificar` existente; solo inserta `NUEVO` con
  folios; nunca verifica, renumera ni reemplaza documentos anteriores.
- ANEXOS: solo `tipo_codigo` del catálogo oficial. Compara número, tipo y
  vencimiento y aplica validación de secuencia del módulo de Monitoreo. Los
  vencidos mantienen su numeración histórica. Registra las recepciones en
  `RegistroCoordinacion` y `AnexoCoordinacion` y, cuando proceda,
  `AnalisisRiesgo` o `ReporteMonitoreo`.
- PAGOS: valida boleta+banco, monto, período, RC/RE, providencia y fecha;
  inserta exclusivamente nuevos pagos en `RegistroCoordinacion` y
  `PagoCoordinacion`. La solvencia la recalcula `pagos_service`.
- Todos: comparación sin escritura, confirmación firmada con vencimiento
  de 30 minutos, mismo archivo y usuario, bloqueo de SP, nueva comparación
  y transacción con bitácora. No almacena PDF, fotografías ni OCR íntegro.

## Importante antes de producción
Esta rama **no está desplegada ni probada** en el servidor. Requiere ejecutar
regresión con base de pruebas y revisión por Codex o ingeniero responsable.
No fusionar el PR v3 (#93) separado: el v4 lo sustituye.

```bash
cd /opt/sicode/app
git fetch origin
git status --short
git switch -c prueba-importmia-v4 origin/feature/importmia-simple-v4
python -m compileall -q app tests
pytest -q tests/test_importmia_simple.py tests/test_importmia.py \
 tests/test_importacion_indice_fileserver.py tests/test_pagos_service.py \
 tests/test_analisis_riesgo_masivo.py tests/test_anexos_inteligentes.py \
 tests/test_indice_documental_foliacion_anexos.py tests/test_security.py
python -m flask --app run.py routes | grep importmia
```

El operador debe revisar y confirmar los estados NUEVO. Los bloqueados y
conflictivos requieren corrección independiente, sin eliminar ni sobrescribir
los registros institucionales existentes.
