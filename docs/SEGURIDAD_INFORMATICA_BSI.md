# Seguridad Informática - Vulnerabilidades y Boletas BSI

## Informes institucionales incorporados al diseño (octubre 2026)

Se revisaron tres informes técnicos de Dirección de Informática / Ministerio de Gobernación, y se creó un catálogo inicial de **19 CVE**, sin copiar sus archivos originales a GitHub.

| Informe | CVE | Controles requeridos |
| --- | ---: | --- |
| Chrome, 30/10/2026 | 9 | Versión y canal, parches, reinicio, extensiones, navegación |
| Java y Python, 30/10/2026 | 8 | Java SE/JavaFX, Python, certificados, TAR, Expat/XML |
| PHP, 21/10/2026 | 2 | PHP web/FPM, rama y versión, parches, pruebas posteriores |

En el informe Python, CVE-2026-77214 / 102633 son dos identificadores separados (CVE-2026-77214 y CVE-2026-102633). Esto fue contrastado con el aviso de libexpat. La categoría MEDIA de Java CVE-2026-91395 reproduce la prioridad del informe (CVSS 6.5). En Python no se infieren calificaciones CVSS donde no se proporcionaron. Un aviso de explotación en un informe no equivale a una entrada en CISA KEV.

Fuentes públicas contrastadas:
- Chrome: https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_02107719452.html y https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_0562499947.html
- Oracle: https://www.oracle.com/security-alerts/cpuoct2026.html
- Python: https://www.python.org/downloads/release/python-31410/
- Expat: https://www.openwall.com/lists/oss-security/2026/10/05/16
- PHP: https://www.php.net/archive/2026.php

### Carga segura del catálogo y de los documentos originales

Después de actualizar y migrar una instancia autorizada, ejecute esta importación idempotente de metadatos:

    cd /opt/sicode/app
    /opt/sicode/venv/bin/python -m flask --app run.py seguridad-cargar-informes-2026

El comando no lee archivos ni hace solicitudes web, no genera 19 alertas históricas y puede repetirse sin duplicar CVE. No modifica una PC ni su estado de afectación.

En Seguridad Informática → Informes recibidos → Cargar informe PDF/DOCX, incorpore cada archivo original, su título y entidad emisora, fecha del informe, fecha real de recibido y la lista de CVE. El sistema vincula los CVE ya existentes, almacena el archivo en una carpeta privada, protege la descarga con login y detecta archivos repetidos mediante SHA-256. El máximo permitido es 8 MB y hasta 100 CVE por documento.

Respaldo obligatorio: la base de datos guarda vínculos y metadatos, pero los adjuntos originales se guardan en disco. El plan de respaldo debe incluir tanto PostgreSQL como la carpeta privada instance/seguridad/avisos_cert, manteniendo permisos y relación entre ambos. Un respaldo de PostgreSQL por sí solo no recupera los archivos cargados.

Cargue un documento por informe: Chrome (9 CVE, informe del 30/10), Java/Python (8 CVE, informe del 30/10) y PHP (2 CVE, aviso del 21/10). Complete la fecha de recibido según el correo recibido, no asuma que coincide con la publicación.

**Los archivos recibidos en este chat NO se copian automáticamente a la instalación productiva ni al repositorio**. Deben subirse desde la pantalla administrativa por personal autorizado después del despliegue. No se recomienda añadir originales institucionales a un repositorio público.

### Revisión por equipo

La nueva boleta tiene listas de Instalado, No instalado o Por verificar para Chrome, Java, Python y PHP, además de campos de versión de SO, Chrome, Java, Python, PHP y antivirus. Los controles de tecnologías ausentes se pueden marcar No aplica. El PDF y el Excel dejan constancia de las versiones y de los resultados, pero no prueban que SICODE haya escaneado el equipo.

## Actualización de boletas BSI · Protocolo Chrome 4.1/4.2 y 19 CVE CERT

La boleta versión 3 incorpora los controles adicionales del formulario CERT recibido para Chrome. Se mantienen, sin duplicar, los controles ya existentes: instalación y versión de Chrome, versión de sistema operativo, actualización, reinicio, navegación segura, extensiones, antivirus/EDR y conectividad general.

Nuevas verificaciones específicas del numeral 4.1: dependencia o responsable (4), fecha de revisión (5), sistemas sensibles (10), actualizaciones automáticas (11), alertas antivirus/EDR de Chrome (12), descargas y procesos sospechosos (13), incidencias y fechas de actuación (14). Nuevas medidas 4.2: reducción temporal de uso (16), archivos inesperados (18), extensiones no oficiales (19), conexión a repositorios de actualización (20), coordinación de instalación administrativa (21). Las recomendaciones sobre sitios no confiables ya estaban contempladas en el control general de navegación segura. El formato de PDF utiliza el checklist íntegro y conserva sus encabezados por grupo.

**Lote institucional predeterminado:** el formulario de nueva boleta incluye marcada la opción "Incluir las 19 vulnerabilidades del CERT"; toma los 19 CVE por identificador exacto de los informes, incluso si el catálogo de CISA y NVD crece a miles. Adicionalmente pueden escogerse hasta 11 CVE globales opcionales (máximo 30). Si alguno de los 19 no se ha cargado, se avisa al usuario; ejecute la importación idempotente documentada anteriormente.

**Ausencias:** al guardar, cuando el técnico selecciona "No instalado" para Chrome, Java, Python o PHP, los CVE institucionales correspondientes quedan en No aplica, con observación de ausencia declarada. Los grupos técnicos específicos de Java, Python, PHP y protocolo Chrome también quedan No aplica. Si una tecnología está instalada, el técnico debe verificar versión y corrección: SICODE nunca presupone que un CVE está corregido. Si una tecnología queda "Por verificar", no se puede finalizar la boleta con CVE de esa tecnología. Se mantiene el checklist de las boletas anteriores sin reescritura retroactiva.

**Eliminar boleta:** se implementa como ANULACIÓN LÓGICA, no un borrado físico. Se exige motivo y confirmación, queda registro en Bitácora, no se reutiliza el folio BSI y desaparece del listado e informe XLSX vigentes. El administrador consulta las anuladas desde el enlace de auditoría. Un técnico puede anular sus propias boletas abiertas; una boleta finalizada solo puede ser anulada por un administrador. Ni la boleta anulada ni su cronómetro pueden modificarse o generar un PDF final.

**Despliegue:** se trata de un cambio de código sin migración de esquema adicional. Conservar la rama compatible con HashPass y validar tests antes de aplicar un nuevo despliegue seguro; no volver a ejecutar la migración inicial ni borrar tablas.

## Modalidad adicional: Medidas prioritarias y temporales

La pantalla **Nueva Boleta de Seguridad Informática** presenta un segundo bloque justo debajo de la selección de los 19 CVE CERT, con el botón **Crear boleta de Medidas Prioritarias y Temporales**.

Esta opción abre un formulario **independiente** que utiliza el mismo inventario de equipos, cronómetro, permisos, historial y numeración BSI-000001, BSI-000002… de las boletas integrales. Es **una nueva boleta**, no un anexo ni una duplicación de los 19 CVE. Ambos tipos comparten la secuencia mediante la misma tabla boletas_seguridad_ti.id y se identifican por el campo tipo_boleta (INTEGRAL o MEDIDAS).

La boleta de medidas únicamente presenta las recomendaciones de los **tres informes enviados por CERT/MINGOB**:

- Google Chrome: **4.1 Acciones prioritarias** (6 verificaciones) y **4.2 Medidas temporales** (3 verificaciones).
- Java/Python: **4.1 Acciones prioritarias** (6 verificaciones) y **4.2 Medidas temporales** (5 verificaciones desglosadas del texto de 4.2).
- PHP: **4.1 Acciones prioritarias** (6 verificaciones) y **4.2 Medidas temporales** (4 verificaciones; las referencias a session.upload_progress.enabled, fatal_error_backtraces, límites y WAF son medidas para evaluación del administrador, no cambios automáticos).

El técnico registra si Chrome, Java, Python y PHP están instalados y su versión. Las medidas de Chrome/PHP se marcan No aplica cuando se declara que el software está ausente. Las medidas conjuntas Java/Python son No aplica **solo cuando ambos están ausentes**. Se exige verificar instalación y responder toda la hoja antes del cierre; No cumple exige observación.

El PDF se titula **BOLETA DE MEDIDAS PRIORITARIAS Y TEMPORALES**, con identificación del equipo, secciones por 4.1/4.2 y tecnología, respuestas, observaciones, tiempo, acciones y firmas. Comparte el mismo folio BSI sin prefijo adicional. El listado general distingue la modalidad y el Excel incluye la columna Modalidad. Las boletas históricas preservan su checklist.

Para despliegue: migración Alembic **simpt20261103**, descendiente de **siuct20261103**; agrega tipo_boleta con valor inicial INTEGRAL a los registros existentes. No elimina ni modifica folios, inventario, ni informes previos. No requiere reimportar los 19 CVE ni cambiar el timer de CISA/NVD. Usar el actualizador seguro con respaldo antes de migrar.

## Arquitectura y alcance

El acceso **Módulos SICODE → Seguridad Informática** presenta dos paneles:

1. Vulnerabilidades registradas: avisos CERT manuales (con PDF técnico opcional), catálogo CISA KEV y CVE recientes de NVD con CVSS >= 7.
2. Control por computadora: selección desde el inventario maestro (equipos_institucionales.id), checklist, cronómetro, numeración BSI-000001, PDF institucional y XLSX masivo.

La implementación conserva los módulos de Inventario Tecnológico, Mantenimientos y Soporte Técnico, sin modificar sus tablas. El checklist incorpora controles de Chrome y navegadores, Windows/sistema operativo, antivirus, firewall, acceso, respaldo y opcionalmente los CVE seleccionados por el técnico. Una CVE publicada mundialmente NO demuestra exposición del equipo.

El informe XLSX incluye tres hojas: Boletas, Hallazgos y Por equipo. Los datos históricos de equipos se almacenan como snapshot, sin duplicar activos físicos.

## Seguridad

- Roles de administración y usuario autorizado: escritura, cierre, registro CERT y exportación Excel. El visor solo consulta y descarga PDF final.
- Formularios protegidos con CSRF; validación de claves de checklist, no conformidades con observación obligatoria y cierre únicamente después de iniciar reloj.
- PDF individual o informe PDF/DOCX multi-CVE con nombre aleatorio fuera de app/static, descarga autenticada y tamaño máximo de 8 MB. Solo boletines técnicos sin documentación sensible. La verificación de cabecera no sustituye el análisis antivirus del archivo recibido.
- Los textos se escapan en HTML y ReportLab. El Excel previene que los campos libres se ejecuten como fórmulas.
- Registrar audit trail por creación, guardado, reloj, cierre, exportaciones y sincronización.

## Sincronizador

La sincronización se ejecuta **fuera de peticiones HTTP** mediante Flask CLI:

    cd /opt/sicode/app
    /opt/sicode/venv/bin/python -m flask --app run.py seguridad-sincronizar

Fuentes públicas fijas:

- CISA KEV: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- NVD CVE API 2.0: https://services.nvd.nist.gov/rest/json/cves/2.0

CISA incluye todo el catálogo de vulnerabilidades con explotación conocida. NVD consulta un período móvil de tres días y solo incorpora CVE CVSS alta o crítica; no es un espejo completo de todas las CVE. El solapamiento reduce pérdidas ante interrupciones. Puede existir retraso en publicación o calificación CVSS.

La primera sincronización inicializa el catálogo sin enviar avisos masivos históricos. Posteriores incorporaciones nuevas o confirmaciones nuevas de explotación crean notificaciones para usuarios autorizados usando el contador actual de Agenda UCT. Si no hay Internet, persiste el catálogo anterior y registra fecha/error en panel.

## Recuperación de un despliegue parcial previo (3 de noviembre de 2026)

La rama de Seguridad original no incluía las revisiones hp00120261029 y hp00220261029, por lo que un servidor con HashPass registraba `Can't locate revision identified by 'hp00220261029'`. No es un fallo de conectividad ni una instrucción para borrar tablas. **No ejecutar `flask db stamp`, `db downgrade` ni crear tablas manualmente.** El despliegue compatible parte de la rama `feature/integracion-hashpass-seguridad-20261103`. El timer de sincronización se mantiene deshabilitado hasta confirmar `flask db current` con `siuct20261103`.

## Instalación diaria

**Antes del despliegue**: respaldo verificable de PostgreSQL, revisión de migraciones en base de pruebas, y aprobación del PR. En la rama de integración HashPass + Seguridad, la migración siuct20261103 depende de hp00220261029, que ya existe en la BD productiva. No usar la rama de Seguridad aislada en servidores con HashPass. Revisar las cabezas Alembic de la rama y del servidor antes de ejecutar upgrade. La base debe estar en hp00220261029 y después de la migración en siuct20261103. Seguir docs/OPERACION_SERVIDOR.md para despliegue seguro.

El servidor documentado usa /opt/sicode/app, virtualenv /opt/sicode/venv y sicode.service. Configure un usuario de sistema real de SICODE antes de instalar las plantillas:

    cd /opt/sicode/app
    SICODE_USER="$(systemctl show -p User --value sicode.service)"
    test -n "$SICODE_USER" || { echo "Debe especificar usuario de servicio"; exit 1; }
    sed -e "s|__SICODE_USER__|$SICODE_USER|g" \
        -e "s|__SICODE_APPDIR__|/opt/sicode/app|g" \
        -e "s|__SICODE_PYTHON__|/opt/sicode/venv/bin/python|g" \
        deploy/systemd/sicode-seguridad.service.template | sudo tee /etc/systemd/system/sicode-seguridad.service >/dev/null
    sudo cp deploy/systemd/sicode-seguridad.timer.template /etc/systemd/system/sicode-seguridad.timer
    sudo systemctl daemon-reload
    sudo systemctl enable --now sicode-seguridad.timer
    systemctl list-timers sicode-seguridad.timer

La tarea se programa a las 07:00 de la zona horaria local del servidor (verifique con timedatectl), con variación aleatoria de hasta diez minutos. El usuario del servicio debe poder escribir en instance/seguridad/avisos_cert, al igual que el proceso web.

Ejecución de diagnóstico:

    sudo systemctl start sicode-seguridad.service
    systemctl status sicode-seguridad.service --no-pager
    journalctl -u sicode-seguridad.service -n 80 --no-pager

Para suspender: sudo systemctl disable --now sicode-seguridad.timer. La tarea no realiza escaneos de computadoras, ni instala parches por sí sola. Necesita salida DNS/HTTPS para dominios oficiales y no abre puertos entrantes.

## Validación mínima

    python -m compileall -q app migrations tests
    python -m flask --app run.py db heads
    pytest -q tests/test_seguridad_operativa_bsi.py tests/test_mantenimientos_control09.py tests/test_agenda_uct.py tests/test_seguridad_inventario_09.py tests/test_soporte_tecnico.py

1. Confirmar que aparece el menú Seguridad Informática sin modificar Inventario Tecnológico ni Mantenimientos.
2. Registrar un aviso CERT de prueba; comprobar que un CVE duplicado es rechazado y que el PDF adjunto se descarga con autenticación.
3. Seleccionar una computadora SICOIN real en la boleta, asociar las vulnerabilidades aplicables y verificar que no se crea otro activo.
4. Iniciar el cronómetro, guardarlo, pausarlo y comprobar continuidad.
5. Registrar un No cumple sin observación: debe rechazar. Completar las respuestas y finalizar.
6. Descargar PDF BSI; revisar firmas, numeración, equipo, CVE, resultados y tiempos.
7. Exportar Excel y revisar las hojas Boletas, Hallazgos y Por equipo.
8. Comprobar visor (solo lectura), notificaciones de Agenda para nuevas vulnerabilidades y que la importación inicial no sature de avisos.
9. Probar funcionamiento del inventario, mantenimiento, Agenda UCT y boleta de soporte en la misma rama.

**No fusionar ni desplegar sin pruebas, respaldo y validación humana.**
