# Ejecución segura de QA en SICODE-UCT

La suite pytest no debe ejecutarse contra la base productiva.

## Ejecución recomendada

Desde `/opt/sicode/app`:

```bash
source /opt/sicode/venv/bin/activate
python -m pytest -q
```

`tests/conftest.py` aplica dos protecciones antes de importar la aplicación:

1. agrega la raíz del proyecto al `sys.path`, evitando errores `ModuleNotFoundError: No module named 'app'`;
2. si `DATABASE_URL` no apunta claramente a una base de pruebas, sustituye la conexión de pytest por una base SQLite temporal en `/tmp`.

Las bases PostgreSQL de integración deben usar un nombre que identifique claramente el entorno de pruebas, por ejemplo `sicode_test`.

No use la base productiva para `db.drop_all()`, `db.create_all()` ni fixtures de pytest.
