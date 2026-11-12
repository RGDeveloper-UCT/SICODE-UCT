# ImportM.IA v1 — Primera entrega segura

## Estado
Rama de desarrollo `feature/importmia-v1`. No se ha desplegado en producción.

## Alcance implementado
- Menú «ImportM.IA» y pantalla `/importmia/`.
- Carga de Excel v3 (máx. 8 MB; 80 MB expandido; 12 000 filas por hoja).
- Revisión de encabezados y hojas operativas del contrato.
- Previsualización conservadora del índice mediante `leer_excel` y `planificar` existentes.
- Estados de conciliación por SP, incluidos registros `SOLO_SICODE`, diferencias y folios sin validar.
- Confirmación opcional **solo de documentos NUEVO del índice**, previa segunda carga idéntica y nueva planificación con bloqueo de expedientes.
- Los documentos nuevos se registran con estado «Pendiente de revisión».
- No se guardan PDF ni se modifican rectificaciones físicas, registros existentes o números de anexos.
- Bitácora de confirmación del índice.

## Limitación deliberada
Las hojas `ANEXOS`, `PAGOS`, `ANALISIS_RIESGO`, `MONITOREO`, `MOVIMIENTOS`,
`EXPEDIENTE_COMPLETO` y `OTROS_DOCUMENTOS` se reconocen y contabilizan para
diagnóstico. **No se escriben todavía en sus tablas de destino**. Esto evita
saltarse las validaciones especializadas de numeración, vencimiento, periodo
pagado y correlativos. No afirmar que el libro completo fue importado.

No se ha realizado ninguna migración de base de datos ni copia digital de archivos.
Tampoco se ha verificado acceso al File Server real ni a la instancia productiva.

## Operación
1. Acceder con usuario `puede_modificar`.
2. Abrir «ImportM.IA» desde el menú principal.
3. Subir el Excel `ImportMIA_Contrato_Produccion_v3.xlsx` completado por Work.
4. Revisar estados del índice y cantidades de las hojas operativas.
5. Corregir discrepancias en sus módulos correspondientes, si aplica.
6. Para agregar **únicamente** las entradas «NUEVO» al índice, subir el mismo Excel de nuevo y confirmar dentro de 30 minutos.

## Pendientes imprescindibles antes del despliegue
- Ejecutar `pytest -q tests/test_importmia.py tests/test_importacion_indice_fileserver.py tests/test_analisis_riesgo_masivo.py tests/test_pagos_service.py` en una base **exclusivamente de pruebas**.
- Verificar el bloque real de navegación, permisos de usuario y formulario CSRF.
- Ejecutar QA manual con el Excel v3 real, primero anonimizado.
- Diseñar adaptadores especializados de importación para pagos, análisis, anexos y demás hojas.
- Persistir una bitácora de lote detallada si se requiere historial independiente por fila (la v1 solo registra bitácora de confirmación de índice).
- Exportador de snapshot de SICODE y comparación completa contra File Server.
- Confirmar que el servidor utiliza la misma revisión Git que la rama base.

## Seguridad de despliegue
NO fusionar ni desplegar hasta ejecutar regresión local. No usar datos sensibles
para pruebas automatizadas. El operador siempre debe resolver discrepancias de
numeración y recepción antes de escribir.

## Base revisada
GitHub `main` commit `7ec82ddf40ded45276c57b912398c303969e5d8c`
del 2026-10-30. Esta referencia NO prueba la versión ejecutada en producción.
