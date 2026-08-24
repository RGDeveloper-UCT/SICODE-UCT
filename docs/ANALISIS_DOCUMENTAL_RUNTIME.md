# Runtime del análisis documental — SICODE-UCT

## Problema corregido

Los PDFs escaneados requieren renderizado de páginas, Tesseract OCR y, opcionalmente, interpretación con Ollama local. En servidores CPU este proceso puede superar el timeout predeterminado de Gunicorn (30 segundos). Cuando eso ocurre Gunicorn termina el worker mientras `pytesseract.image_to_data()` espera a Tesseract y el navegador recibe HTTP 500.

## Política de ejecución

- Gunicorn: `timeout 600`, `graceful-timeout 30`.
- Nginx: `proxy_read_timeout` y `proxy_send_timeout` de 600 segundos.
- El límite de carga recomendado sigue siendo 50 MB en Nginx y 40 MB en el motor documental.
- La segunda pasada OCR queda desactivada por defecto en servidores CPU. Puede activarse con `DOCUMENT_ANALYSIS_OCR_SECOND_PASS=true` para documentos especialmente difíciles.
- La IA documental usa por defecto un máximo de 12 000 caracteres OCR y 75 segundos para Ollama. Esto reduce el tiempo total sin cambiar la regla de validación humana.
- El PDF, las imágenes renderizadas y el texto OCR completo continúan siendo temporales y se eliminan al finalizar el análisis.

## Instalación

Desde `/opt/sicode/app`:

```bash
sudo bash scripts/configurar_runtime_analisis_documental.sh
```

El script instala únicamente drop-ins/configuración de runtime; no sustituye el archivo principal de `sicode.service` ni la configuración principal de Nginx.

## Configuración recomendada `.env`

```env
DOCUMENT_ANALYSIS_TESSERACT_CMD=/usr/bin/tesseract
DOCUMENT_ANALYSIS_OCR_SECOND_PASS=false
DOCUMENT_ANALYSIS_AI_ENABLED=true
DOCUMENT_ANALYSIS_AI_TIMEOUT=75
DOCUMENT_ANALYSIS_AI_MAX_CHARS=12000
```

## Diagnóstico

```bash
systemctl show sicode.service -p Environment
sudo nginx -T 2>/dev/null | grep -E 'client_max_body_size|proxy_(connect|send|read)_timeout|send_timeout'
sudo journalctl -u sicode.service --since '15 minutes ago' --no-pager
```

Un análisis válido ya no debe terminar con `WORKER TIMEOUT`, `handle_abort` o `SystemExit: 1` provocado por el timeout de Gunicorn.
