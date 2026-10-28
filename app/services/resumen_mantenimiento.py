"""Resumen determinístico, sin IA ni afirmaciones ajenas al checklist."""
def resumen_trabajo(checklist, respaldo_mb=None):
    lineas = []
    grupos = {}
    hallazgos = []
    for fila in checklist or []:
        estado = fila.get("resultado")
        grupo = fila.get("grupo_nombre", "Otros controles")
        actividad = fila.get("actividad", "Actividad")
        if estado == "CUMPLE":
            grupos.setdefault(grupo, []).append(actividad)
        elif estado == "NO_CUMPLE":
            obs = (fila.get("observacion") or "").strip()
            hallazgos.append((grupo, actividad, obs))
    for grupo, actividades in grupos.items():
        lineas.append(f"{grupo}: se verificó cumplimiento en " + "; ".join(actividades) + ".")
    if respaldo_mb is not None:
        lineas.append(f"Tamaño del respaldo declarado: {respaldo_mb} MB.")
    if hallazgos:
        lineas.append("CONTROLES QUE NO CUMPLIERON:")
        for grupo, actividad, obs in hallazgos:
            lineas.append(f"- {grupo} / {actividad}: NO CUMPLE. Hallazgo/acción informada: {obs}")
    else:
        lineas.append("No se reportaron controles marcados como No cumple.")
    return "\n".join(lineas)
