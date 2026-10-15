# SICODE NEXO V2 — aprendizaje supervisado y normalización explicable

## Objetivo

NEXO V2 convierte el panel actual de auditoría técnica en un motor de mejora continua que aprende únicamente de verificaciones humanas y trabaja con metadatos seguros.

Principio rector:

> NEXO recomienda; una persona decide.

NEXO no corrige expedientes automáticamente, no conserva PDF, imágenes ni OCR completo y no debe promover valores desconocidos a catálogos institucionales sin validación funcional.

## Problema corregido

La versión anterior podía observar segmentos de SICODE.IA y mostrar objetos estudiados, pero el aprendizaje dependía de una marca histórica específica (`datos_detectados.modo == SICODE_IA`). Esto podía dejar verificaciones válidas fuera del absorbedor y producir una lectura poco clara de `0 muestras`.

NEXO V2 reconoce de forma compatible las señales históricas de SICODE.IA, conserva idempotencia por Bitácora y expone una cola con:

- segmentos verificados;
- segmentos aprendidos;
- verificaciones pendientes de incorporar;
- segmentos pendientes de validación humana.

## Normalización inteligente local

Se incorpora RapidFuzz para comparar valores de catálogo sin enviar información fuera del servidor.

Antes de recomendar una categoría nueva, NEXO clasifica el valor como:

1. valor canónico;
2. variante ortográfica;
3. alias probable;
4. valor especial (`No aplica`, etc.);
5. texto libre probable en un campo estructurado;
6. combinación de categorías existentes;
7. candidato a nueva categoría;
8. requiere revisión humana.

La salida es explicable: conserva similitud, frecuencia, acción sugerida y valor canónico cuando corresponde.

## Privacidad reforzada

Si NEXO detecta texto libre probable dentro de un campo de catálogo, la memoria portable no repite su contenido. Exporta únicamente:

- marcador `[texto libre omitido]`;
- frecuencia;
- longitud;
- número aproximado de palabras;
- huella SHA-256 truncada para poder reconocer recurrencia sin exponer el texto.

La exportación portable pasa a formato 3 y reanaliza hallazgos históricos de catálogo antes de incluirlos.

## Dependencia instalada por el proyecto

```text
rapidfuzz==3.14.6
```

La aplicación conserva un respaldo basado en `difflib` si la dependencia aún no está disponible durante una transición de despliegue. En producción debe instalarse normalmente mediante `requirements.txt`.

## Despliegue institucional

Seguir siempre `docs/OPERACION_SERVIDOR.md`.

Después de integrar a `main`:

```bash
cd /opt/sicode/app
git status
git fetch origin
git pull --ff-only origin main

source /opt/sicode/venv/bin/activate
pip install -r requirements.txt

python -m compileall -q app migrations tests
pytest -q tests/test_nexo_catalogo_service.py

sudo systemctl restart sicode.service
sleep 2
systemctl status sicode.service --no-pager
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

No hay migración nueva de base de datos en esta fase.

## Validación funcional

1. Abrir SICODE NEXO como administrador.
2. Confirmar PostgreSQL y RapidFuzz como disponibles.
3. Revisar el KPI de verificaciones aprendidas.
4. Revisar el texto de la cola de aprendizaje.
5. Confirmar que errores ortográficos se propongan contra un valor canónico.
6. Confirmar que `No aplica` no se sugiera como categoría institucional.
7. Confirmar que texto libre probable no aparezca íntegro en el panel ni en la exportación.
8. Exportar memoria NEXO y confirmar `version_formato: 3`.
9. Confirmar que NEXO no modificó registros operativos automáticamente.

## Integraciones investigadas para una segunda etapa

### PostgreSQL `pg_trgm`

Útil para similitud y búsquedas aproximadas directamente en PostgreSQL, con soporte de índices GiST/GIN. Se recomienda evaluarlo cuando la normalización de catálogos deba operar sobre volúmenes mucho mayores o se quiera compartir la misma lógica de similitud con la búsqueda global.

No es obligatorio para NEXO V2 porque el volumen actual puede resolverse localmente con RapidFuzz sin cambios de esquema.

### scikit-learn `SGDClassifier.partial_fit`

Permite aprendizaje incremental/online. Puede convertirse en una segunda capa del clasificador documental una vez exista suficiente retroalimentación humana real.

No debe activarse con una muestra vacía o mínima. Antes de introducirlo conviene tener un conjunto representativo por varias categorías y comparar su precisión contra las reglas explicables actuales.

### Sentence Transformers

Permite embeddings y similitud semántica. Puede ser útil más adelante para alias semánticos difíciles, pero implica modelos y dependencias más pesadas. No se incorpora en esta fase porque NEXO debe resolver primero su circuito de aprendizaje supervisado y porque no se desea ampliar innecesariamente el tratamiento de texto documental.

## Criterio para la siguiente fase

Evaluar clasificador incremental cuando NEXO tenga, como mínimo orientativo:

- 50 o más verificaciones aprendidas;
- al menos 3 tipos documentales con ejemplos confirmados;
- varias muestras por tipo, evitando clases con un único ejemplo;
- precisión y tasa de reclasificación medibles durante uso real.

La adopción debe hacerse mediante comparación A/B contra el clasificador actual, sin sustituirlo directamente y manteniendo siempre verificación humana para cambios de categoría.
