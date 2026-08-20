# Búsqueda con IA local — SICODE-UCT

## Objetivo

Agregar al panel `/buscar` una segunda modalidad de consulta en lenguaje natural, manteniendo la búsqueda manual como mecanismo principal y sin permitir que el modelo modifique datos.

## Arquitectura

1. El usuario escribe una consulta en el panel de búsqueda.
2. SICODE envía únicamente el texto de esa consulta al servicio Ollama configurado en `127.0.0.1`.
3. El modelo devuelve un objeto JSON con filtros dentro de un esquema cerrado.
4. `busqueda_ia_service.py` normaliza y descarta cualquier campo no autorizado.
5. SICODE construye las consultas usando SQLAlchemy y modelos conocidos; el modelo nunca genera ni ejecuta SQL.
6. Los resultados se muestran con enlaces a los registros reales de SICODE.
7. La consulta, filtros aplicados, motor utilizado y cantidad de resultados quedan registrados en Bitácora.

Si Ollama no responde, SICODE conserva el panel operativo y utiliza un intérprete básico por reglas para consultas frecuentes.

## Seguridad

- No existe una ruta de IA para crear, editar o borrar información.
- La IA no puede prestar ni devolver expedientes.
- No se almacenan documentos completos para esta función.
- Ollama se configura por defecto en `http://127.0.0.1:11434`.
- Los filtros aceptados están definidos en una lista cerrada.
- Campos devueltos por el modelo como `sql`, `endpoint`, comandos u otros datos no reconocidos se descartan.
- Todas las consultas IA se registran como `CONSULTA_IA` en el módulo `BÚSQUEDA` de Bitácora.

## Modelo recomendado inicial

Para el servidor local se utiliza por defecto:

```bash
qwen3:1.7b
```

Es suficientemente pequeño para una primera implementación y puede sustituirse mediante variable de entorno si el hardware permite un modelo mayor.

## Instalación de Ollama en Linux

En el servidor:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b
```

Comprobar que Ollama responde:

```bash
curl http://127.0.0.1:11434/api/tags
```

## Variables de entorno

Los valores por defecto permiten operar sin modificar `.env` cuando Ollama está instalado en el mismo servidor.

```env
AI_SEARCH_ENABLED=true
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_TIMEOUT=15
```

No configurar `OLLAMA_URL` con una dirección pública para el entorno institucional salvo que exista una decisión técnica formal y controles equivalentes de seguridad.

## Consultas esperadas

- `¿Dónde está el expediente del SP 11?`
- `Muéstrame los préstamos vencidos.`
- `¿Quién tuvo por última vez el expediente del SP 38?`
- `Alertas pendientes de gravedad alta.`
- `Anexos del SP 24.`
- `Busca instalaciones del SP 50.`
- `Busca la providencia 123-2026.`

## Pruebas

La cobertura automatizada se encuentra en `tests/test_busqueda_ia.py` e incluye:

- normalización del No. de SP;
- rechazo de campos no autorizados;
- consulta estructurada de préstamos vencidos;
- renderizado de la ruta de IA;
- registro de la consulta en Bitácora.

La prueba no requiere que Ollama esté instalado: la respuesta del modelo se simula para validar de forma determinista la integración de SICODE.
