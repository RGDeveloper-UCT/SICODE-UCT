# SICODE-UCT

Sistema de Control y Ordenamiento de Expedientes de la Unidad de Control Telemático.

Aplicación web interna desarrollada en Python para registrar, buscar, ubicar, controlar, verificar y dar seguimiento a expedientes físicos mediante metadatos administrativos, ubicación física, foliación, préstamos, devoluciones, alertas, reportes y bitácora.

## Restricción principal

El sistema no debe almacenar documentos sensibles ni copias completas de expedientes físicos. Solo debe registrar metadatos administrativos y de control.

## Tecnología base

- Python
- Flask
- PostgreSQL
- SQLAlchemy
- Flask-Migrate
- Flask-Login
- HTML / Bootstrap
- Reportes PDF y Excel
- Servidor local institucional

## Módulos actuales

- Dashboard.
- Expedientes y ubicación física.
- Índice documental y foliación.
- Préstamos y devoluciones.
- Alertas.
- Bitácora.
- Administración y respaldos.
- Coordinación: registro operativo de pagos, instalaciones, desinstalaciones, anexos, reportes de monitoreo, documentos emitidos, actividades y remisiones.

## Importación histórica de Coordinación

El módulo Coordinación permite previsualizar e importar las hojas operativas del libro histórico de actividades. La importación conserva archivo, hoja y fila de origen, permite datos incompletos y marca los SP todavía no existentes en Expedientes como pendientes de vincular.

Las hojas Portadores y VERIFICACIONES no se modifican ni importan desde este módulo; su integración corresponde a la ampliación posterior de la ficha maestra de Expedientes.

## Estado actual

Aplicación Flask operativa en ambiente institucional, con desarrollo versionado mediante Git.
