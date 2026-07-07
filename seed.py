import os
from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models.usuario import Usuario

app = create_app()

usuarios_iniciales = [
    {
        "nombre": "Hans",
        "usuario": "hans",
        "correo": "hans@uct.local",
        "rol": "administrador",
    },
    {
        "nombre": "Ronny",
        "usuario": "ronny",
        "correo": "ronny@uct.local",
        "rol": "usuario_autorizado",
    },
    {
        "nombre": "Will",
        "usuario": "will",
        "correo": "will@uct.local",
        "rol": "usuario_autorizado",
    },
    {
        "nombre": "Nat",
        "usuario": "nat",
        "correo": "nat@uct.local",
        "rol": "usuario_autorizado",
    },
]

password_temporal = os.getenv("SEED_PASSWORD")

if not password_temporal:
    raise RuntimeError("Debe configurar SEED_PASSWORD en el archivo .env")

with app.app_context():
    for item in usuarios_iniciales:
        existe = Usuario.query.filter_by(usuario=item["usuario"]).first()

        if existe:
            print(f"Usuario ya existe: {item['usuario']}")
            continue

        nuevo_usuario = Usuario(
            nombre=item["nombre"],
            usuario=item["usuario"],
            correo=item["correo"],
            password_hash=generate_password_hash(password_temporal, method="pbkdf2:sha256"),
            rol=item["rol"],
            activo=True,
        )

        db.session.add(nuevo_usuario)
        print(f"Usuario creado: {item['usuario']}")

    db.session.commit()
    print("Carga inicial finalizada.")
    print("Contraseña temporal cargada desde .env")
