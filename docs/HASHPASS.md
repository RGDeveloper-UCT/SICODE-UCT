# HashPass HP-001 — Integración y evaluación de seguridad

Estado: **rama de desarrollo / NO APROBADO PARA PRODUCCIÓN**.
Fecha: 2026-10-29. Responsable: equipo SICODE-UCT.

## Alcance implementado

- Integración con Flask y PostgreSQL / Flask-Migrate.
- Botón **Conceder permiso HashPass / Revocar HashPass** en Administración → Usuarios, exclusivo de administrador.
- Acceso por servidor (403 aun cuando se intente introducir la ruta manualmente). Un administrador **no obtiene automáticamente acceso a bóvedas ajenas**.
- Bóvedas privadas por usuario. Contraseña maestra distinta de SICODE; se solicita para cada operación sensible.
- Argon2id (64 MiB / 3 iteraciones / paralelismo 2), DEK aleatoria de 256 bits envuelta con AES-256-GCM.
- AES-256-GCM por registro con nonce aleatorio de 96 bits, autenticación asociada a usuario e ID.
- Contenido cifrado: nombre, usuario, contraseña, URL, IP, host, notas y campos especializados. Metadatos en claro mínimos: categoría, propietario, UUID y fechas.
- Formulario variable de web, aplicación, servidor, red, BD, correo, API, Wi-Fi, servicio y personalizado.
- Crear, consultar, sustituir, archivar, cambiar contraseña maestra, generador CSPRNG.
- Auditoría de accesos, otorgamientos, revocaciones, cambios y revelaciones con la bitácora existente.

## Decisión criptográfica y modelo de amenaza (ADR-HP001)

**Opción preferible para seguridad máxima:** integrar un gestor de secretos maduro, mantenido, auditable y con políticas de recuperación claramente definidas. **Opción implementada para validación:** bóveda privada propia, aislada lógicamente de expedientes, con algoritmos estándar vía librerías mantenidas.

La opción propia permite el flujo integrado SICODE, pero requiere **revisión criptográfica y pruebas de penetración independientes** antes de guardar claves reales. No es equivalente a KeePass/KDBX.

La contraseña maestra **sí llega transitoriamente al backend** al crear/desbloquear/sustituir datos. El servidor descifra en memoria durante esa petición. Por ello NO existe cifrado extremo a extremo contra un administrador del servidor comprometido. Un actor con control de la aplicación web puede capturar la maestra; TLS solo protege tránsito. Ni una contraseña maestra fuerte ni AES solucionan este riesgo.

No existe recuperación silenciosa: perder la maestra implica perder acceso a la bóveda (sin mecanismo aprobado de recuperación). El administrador no la establece ni la conoce. Cambiar la maestra reenvuelve la clave de la bóveda.

**Límites actuales que impiden llamar a esto producción auditada:**
- Sin auditoría criptográfica independiente ni pruebas de penetración.
- No incorpora bóvedas compartidas ni sincronización KDBX.
- La bitácora existente es transaccional, pero no tiene protección criptográfica de integridad frente a un administrador de BD; requiere log append-only externo.
- No se implementa exportación/restauración específica de bóvedas, custodia de claves de emergencia ni recuperación institucional.
- La interfaz vuelve a solicitar maestra para cada operación, en lugar de persistirla. No guarda claves en cookie, sesión, Redis ni localStorage.
- El servidor actual documenta Nginx en HTTP/80. **Habilitar HTTPS con certificado institucional válido antes de activar el módulo.**
- Revisión pendiente sobre las políticas de log de Nginx/Gunicorn, respaldos PostgreSQL, permisos SQL por esquema y seguridad de estaciones.

## Migración de pruebas / staging

Ejecute estos pasos en una **copia autorizada de pruebas**, no directamente en la base de producción:

```bash
cd /opt/sicode/app
git status --short
git fetch origin
git switch -c feature/hashpass-hp001 --track origin/feature/hashpass-hp001
source /opt/sicode/venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q tests/test_hashpass.py
python -m compileall -q app migrations tests
python -m flask --app run.py db current
python -m flask --app run.py db heads
python -m flask --app run.py db upgrade
python -m flask --app run.py db current
```

Antes de activar el módulo en staging, copie su BD productiva únicamente si la política institucional lo autoriza y con datos desensibilizados. **Nunca ejecute las pruebas sobre la BD real**; `tests/conftest.py` intenta proteger automáticamente la suite, pero verifique `DATABASE_URL`.

Configuración propuesta tras instalar y validar HTTPS:

```dotenv
HASHPASS_ENABLED=true
HASHPASS_REQUIRE_HTTPS=true
# Sólo cuando Gunicorn está ligado a 127.0.0.1 y Nginx es único proxy:
HASHPASS_PROXY_PROTO_COUNT=1
```

Estas variables se añaden al `.env` LOCAL del servidor, **nunca a Git**. No coloque claves ni contraseñas institucionales en el repositorio.

Configurar Nginx para servir HTTPS (443) con un certificado de confianza de los equipos clientes; establecer:
```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```
en el bloque que reenvía a Gunicorn ligado **exclusivamente a 127.0.0.1**. Redirija puerto 80 a 443. Valide cabeceras, acceso desde clientes y que `request.is_secure` sea verdadero. No active `HASHPASS_PROXY_PROTO_COUNT=1` si Gunicorn es accesible por la LAN o un cliente puede falsificar cabeceras del proxy.

Reinicie SICODE y compruebe el servicio y las rutas existentes con el procedimiento de `docs/OPERACION_SERVIDOR.md`.

## Pruebas funcionales de aceptación (staging)

1. Como administrador, conceda HashPass a una cuenta de prueba activa.
2. Verifique que usuarios no autorizados reciben 403 en `/hashpass/`.
3. Inicie con el usuario autorizado, cree una maestra **ficticia** de al menos 15 caracteres y distinta de SICODE.
4. Registre web, AP/equipo, servidor y API ficticios; confirme que se almacenan como ciphertext y nunca en logs.
5. Compruebe que la revelación exige maestra correcta y produce bitácora.
6. Confirme que un segundo usuario, aun con HashPass, recibe 404 por ID ajeno.
7. Compruebe bloqueo temporal tras cinco contraseñas maestras fallidas en diez minutos.
8. Revocar permiso y verificar 403 inmediato (no se destruye la bóveda).
9. Ejecute el conjunto previo de regresión SICODE y verifique los reportes/respaldos existentes.
10. Restauración de respaldo cifrado/asegurado en una base temporal y revisión de permisos de ficheros.

## Rollback y cuidados especiales

La migración permite `downgrade` **únicamente si no hay bóvedas ni registros creados**. Nunca ejecute downgrade destructivo sobre un almacén con secretos; utilice snapshot de BD, revisión de dependencias y procedimiento institucional.

Para deshabilitar acceso inmediatamente: `HASHPASS_ENABLED=false` en `.env`, reinicio del servicio. Ello NO borra credenciales ni cifrados, y los respaldos deben mantenerse bajo protección.

**Importante:** en la instalación actual los backups administrativos de PostgreSQL se guardan como `.sql` y se pueden descargar desde Administración; incluso cuando las credenciales HashPass estén cifradas en ese dump, debe protegerse el archivo y limitar el acceso. No usar esta funcionalidad en producción sin política formal de backups cifrados, retención, almacenamiento y restauración.

## Puntos de revisión para ingeniería

- Evaluar protección del material criptográfico ante volcados de memoria y excepciones.
- Validar que las cabeceras y CSP no rompen el resto de la aplicación.
- Revisión de dependencia y vulnerabilidades de `cryptography` y `argon2-cffi`.
- Ensayar restauraciones en staging, verificar contingencia de pérdida de maestra.
- Someter extensión del alcance SICODE a aprobación documental (el proyecto original excluía material sensible).
