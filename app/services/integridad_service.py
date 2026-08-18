from app.checks import backups, coordinacion, expedientes, folios, prestamos, usuarios


REGLAS = (
    ("Expedientes", expedientes.ejecutar),
    ("Foliación", folios.ejecutar),
    ("Préstamos", prestamos.ejecutar),
    ("Coordinación", coordinacion.ejecutar),
    ("Usuarios", usuarios.ejecutar),
    ("Backups", backups.ejecutar),
)


def ejecutar_control_integridad():
    hallazgos = []
    modulos_correctos = []

    for nombre, regla in REGLAS:
        resultados = regla()
        hallazgos.extend(resultados)
        if not resultados:
            modulos_correctos.append(nombre)

    errores = [item for item in hallazgos if item.severidad == "error"]
    advertencias = [item for item in hallazgos if item.severidad == "advertencia"]

    return {
        "total_reglas": len(REGLAS),
        "modulos_correctos": modulos_correctos,
        "correctos": len(modulos_correctos),
        "errores": len(errores),
        "advertencias": len(advertencias),
        "hallazgos": sorted(
            hallazgos,
            key=lambda item: (0 if item.severidad == "error" else 1, item.modulo, item.codigo, item.registro),
        ),
    }
