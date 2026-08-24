# Lote documental inteligente — SICODE-UCT

## Objetivo

El módulo trata un PDF como un lote que puede contener múltiples piezas documentales. El binario se conserva únicamente durante el procesamiento y se elimina al terminar el análisis.

## Flujo

1. Lectura de texto nativo por página.
2. OCR local Tesseract únicamente en páginas sin texto suficiente.
3. Clasificación por señales documentales y pesos aprendidos.
4. IA local Ollama como segunda opinión para tipo e inicio de documento.
5. Agrupación de páginas en piezas lógicas.
6. Extracción independiente de metadatos por pieza.
7. Bandeja de validación humana.
8. Creación del registro operativo o del índice documental solo después de confirmar.

Tipos iniciales: Pago, Providencia, Anexo, IFT, Acta, DPI, Instalación, Desinstalación, Monitoreo, Oficio, Informe, Resolución, Formulario y Otro.

## Privacidad

No se persisten:

- PDF original o PDF dividido.
- imágenes renderizadas;
- texto OCR completo;
- nombre original del archivo;
- texto usado como prompt de Ollama;
- nombre, CUI, dirección, fecha de nacimiento u otros datos personales extraídos de un DPI.

DPI puede clasificarse como pieza documental, pero su propuesta inicial se reduce a tipo y rango de páginas. La asociación administrativa que un usuario confirme posteriormente se considera una decisión humana separada.

## Aprendizaje

El sistema no reentrena automáticamente a Ollama ni crea un modelo con los expedientes. La retroalimentación funciona con estadísticas y pesos de características predefinidas, por ejemplo `kw_boleta`, `kw_providencia`, `kw_acta` y `kw_dpi`.

Cuando una persona confirma o corrige el tipo de una pieza:

- aumenta el contador de muestras del tipo confirmado;
- se registra si la clasificación original fue correcta o corregida;
- se comparan campos administrativos propuestos/confirmados;
- se ajustan pesos de las características seguras presentes;
- esos pesos participan en la clasificación de lotes futuros.

El indicador visual del cerebro representa **madurez de retroalimentación**, combinando volumen de ejemplos y tasa de confirmación. No equivale a una probabilidad certificada de exactitud.

## Confirmación humana

No hay escritura automática directa desde OCR/IA a los registros definitivos. Cada pieza permanece en `PENDIENTE_VALIDACION` hasta que un usuario autorizado la confirme o descarte.

Los tipos operativos compatibles con Coordinación pueden crear sus registros existentes. Los demás tipos pueden incorporarse al índice documental si se confirma expediente y rango de folios sin solapamiento.
