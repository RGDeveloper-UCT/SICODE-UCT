# Operación segura del servidor SICODE-UCT

Este procedimiento corresponde a la instalación institucional conocida:

- Código productivo: `/opt/sicode/app`
- Entorno virtual: `/opt/sicode/venv`
- Servicio: `sicode.service`
- Gunicorn: `127.0.0.1:8000`
- Nginx: puerto `80` en la LAN

No copie archivos manualmente sobre producción si el clon Git se encuentra limpio. Utilice Git + migraciones.

## 1. Antes de actualizar

1. Informe a los usuarios que habrá una interrupción breve.
2. Genere un respaldo desde **Sistema → Backups**.
3. Compruebe que el archivo aparece con tamaño mayor que cero.
4. No continúe si no dispone de un respaldo reciente.

En terminal:

```bash
cd /opt/sicode/app
git status
```

Debe indicar un árbol de trabajo limpio. Si existen cambios locales, no ejecute `git pull` hasta revisarlos.

## 2. Verificar configuración crítica sin mostrar secretos

```bash
cd /opt/sicode/app

grep -q '^SECRET_KEY=.' .env && echo 'SECRET_KEY configurada' || echo 'FALTA SECRET_KEY'
grep -q '^DATABASE_URL=.' .env && echo 'DATABASE_URL configurada' || echo 'FALTA DATABASE_URL'
```

No use `cat .env` en capturas o chats.

## 3. Actualizar código

```bash
cd /opt/sicode/app
git fetch origin
git pull --ff-only origin main
git log -1 --oneline
```

## 4. Actualizar dependencias

```bash
source /opt/sicode/venv/bin/activate
cd /opt/sicode/app
pip install -r requirements.txt
```

## 5. Revisar y aplicar migraciones

```bash
python -m flask --app run.py db current
python -m flask --app run.py db heads
python -m flask --app run.py db upgrade
python -m flask --app run.py db current
```

### Migraciones de integridad

La revisión `e8b7c4d2a190` contiene comprobaciones previas. Si detecta:

- rangos de folios inválidos;
- más de un préstamo activo para el mismo expediente;
- SP repetido dentro de una misma remisión;

**la migración se detendrá a propósito antes de aplicar los constraints.** No la fuerce ni edite Alembic manualmente. Revise los registros indicados y corrija los datos con trazabilidad.

La revisión `f4a1c9e2d730` obliga a los usuarios activos a cambiar su contraseña temporal en el siguiente acceso. No modifica ni revela hashes existentes.

## 6. Reiniciar la aplicación

```bash
sudo systemctl restart sicode.service
sleep 2
systemctl status sicode.service --no-pager
```

Debe mostrar `active (running)`.

## 7. Health checks

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/db
```

El primero debe indicar estado `ok` y versión. El segundo debe indicar conexión correcta a PostgreSQL.

Después valide desde una PC cliente:

```text
http://192.168.133.10
```

La IP puede cambiar si la red institucional cambia; confirme con `ip -br addr` en el servidor.

## 8. Prueba funcional mínima posterior al despliegue

1. Iniciar sesión.
2. Cambiar contraseña si el sistema lo exige.
3. Abrir Dashboard.
4. Buscar un SP conocido desde **Buscar**.
5. Abrir **SP / Expedientes**.
6. Abrir **Coordinación**.
7. Administrador: abrir **Sistema → Control de Integridad**.
8. Confirmar que un usuario no administrador no puede importar Portadores ni acceder a administración.

No importe una manta masiva hasta terminar esta prueba básica.

## 9. Rollback

No ejecute `flask db downgrade` a ciegas en producción.

Si falla el código antes de una migración, puede regresar al commit anterior con Git después de identificarlo.

Si una migración ya modificó la base y se requiere una reversión real, el procedimiento seguro es:

1. detener SICODE;
2. conservar una copia de la base actual para diagnóstico;
3. restaurar el backup previo al despliegue;
4. volver al commit de código correspondiente a ese backup;
5. arrancar y validar.

La reversión debe tratar **código y base de datos como una misma versión**.

## 10. Prueba de restauración de backup

Nunca pruebe restauración sobre la base productiva.

Durante una ventana de mantenimiento y con credenciales PostgreSQL autorizadas, cree una base temporal, por ejemplo:

```text
sicode_restore_test_YYYYMMDD
```

Restaure el `.sql` con `psql --set ON_ERROR_STOP=on`, compruebe que las tablas principales existen y compare conteos de tablas críticas (`usuarios`, `expedientes`, `registros_coordinacion`, `bitacora`). Luego elimine la base temporal.

Esta prueba debe hacerse periódicamente. Un archivo de backup que nunca ha sido restaurado no constituye por sí solo evidencia suficiente de recuperabilidad.

## 11. Diagnóstico básico

Servicio:

```bash
systemctl status sicode.service --no-pager
journalctl -u sicode.service -n 100 --no-pager
```

Nginx:

```bash
systemctl status nginx --no-pager
sudo nginx -t
sudo ss -ltnp | grep -E ':80|:443|:8000'
```

Red:

```bash
ip -br addr
```

Gunicorn debe permanecer ligado a `127.0.0.1:8000`; Nginx es quien publica SICODE a la LAN.
