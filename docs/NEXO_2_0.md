# SICODE NEXO 2.0 — Operación institucional

NEXO es un asistente administrativo para **metadatos agregados**. No lee
expedientes completos, ni conserva PDFs, OCR, nombres de SP o chats. Se mantiene
el diseño Flask/PostgreSQL y la IA local Ollama. Sólo el rol **administrador**
puede acceder a la UI, API de chat, informes, propuestas y motor del cerebro.

## Componentes

- Aprendizaje documental: muestra el volumen y precisión de verificaciones
  humanas de SICODE.IA. El porcentaje de madurez es un indicador de muestras
  y fiabilidad, **no una medida general de inteligencia**.
- Procesamiento pendiente: lotes con cursor persistido en bitácora; no se
  detiene en los 1.000 registros históricos ya procesados.
- Indicadores agregados: expediente físico, rectificación, rangos inválidos,
  préstamos vencidos y alertas abiertas.
- Memoria NEXO: tabla nexo_propuestas, evidencia cuantitativa, estados
  nueva / en_revision / aprobada / descartada / implementada. Las decisiones
  humanas quedan auditadas y una revisión posterior no reabre una propuesta.
- Chat: preguntas de hasta 600 caracteres, contexto estrictamente agregado.
  El único modelo invocado es Ollama local, sin comandos, sin SQL libre y sin
  enviar documentos. Si el modelo falla hay un resumen basado en reglas.
- Informe JSON: ruta administrativa /nexo/informe.

Las recomendaciones se basan en reglas comprobables. Una respuesta generativa
no es prueba suficiente para modificar datos; debe validarse contra los módulos
operativos y procedimientos de control interno.

## Preparación de la actualización

1. Generar y verificar un **backup restaurable** de PostgreSQL.
2. Actualizar SICODE mediante el procedimiento institucional
   scripts/actualizar_servidor_seguro.sh.
3. Ejecutar la migración Alembic con python -m flask --app run.py db upgrade.
4. Confirmar que existe la tabla nexo_propuestas.
5. Ingresar con un administrador, abrir Administración > NEXO y ejecutar
   una revisión de prueba. Confirmar que el usuario autorizado/visor obtiene
   403 en /nexo/estado, /nexo/chat y /nexo/propuestas.
6. Comprobar Ollama: el panel muestra disponibilidad. El chat seguirá
   funcionando en modo de reglas si el modelo local no responde.

Opcionales en .env (sin modificar las claves preexistentes):

    NEXO_OLLAMA_MODEL=qwen3:1.7b
    NEXO_OLLAMA_TIMEOUT=25

El modelo indicado debe estar instalado en Ollama. Su tamaño debe ajustarse a
la memoria/capacidad real del servidor.

## Programación diaria opcional con systemd

Los archivos deploy/systemd/sicode-nexo.*.template tienen marcadores:
__SICODE_USER__, __SICODE_APPDIR__, __SICODE_PYTHON__. Sustituya según el
servidor (por ejemplo /opt/sicode/app y /opt/sicode/venv/bin/python), revise
las rutas antes de instalarlos como /etc/systemd/system/sicode-nexo.service y
/etc/systemd/system/sicode-nexo.timer. Luego, como operador autorizado:

    sudo systemctl daemon-reload
    sudo systemctl enable --now sicode-nexo.timer
    systemctl list-timers --all | grep sicode-nexo
    sudo systemctl start sicode-nexo.service
    journalctl -u sicode-nexo.service -n 60 --no-pager

Puede probar manualmente en el entorno virtual:

    python -m flask --app run.py nexo-revisar

No se instala ni habilita ningún timer automáticamente al desplegar código.
Se debe activar después de comprobar respaldo, migración y rendimiento.
La ejecución CLI registra NEXO_REVISION_AUTOMATICA en bitácora.

## Alcance y límites

- La memoria de NEXO conserva evidencia agregada y decisiones del admin,
  **no el contenido de las preguntas**. El chat de la pestaña sólo se conserva
  en su DOM mientras siga abierta.
- NEXO no edita expedientes, anexos, usuarios, folios ni código.
- La integración de GitHub mostrada en el panel es informativa y no implica
  que el servidor tenga conexión/credenciales para modificar repositorios.
- Las recomendaciones detectan condiciones observables; no sustituyen una
  validación documental ni una evaluación institucional.
- Ante errores en una fase, /nexo/estado mantiene el diagnóstico de las demás.
- El modelo de Ollama no aprende por entrenamiento automático. Lo que
  evoluciona es la memoria de patrones, muestras confirmadas y decisiones.
