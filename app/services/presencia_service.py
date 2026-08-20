import secrets
from collections import defaultdict
from datetime import datetime, timedelta

from flask import current_app, session

from app import db
from app.models.presencia import PresenciaUsuario


SESION_CLAVE = "uo_sesion_id"


def _ahora():
    return datetime.utcnow()


def _ttl_segundos():
    return int(current_app.config.get("UO_ONLINE_TTL_SECONDS", 120))


def _limite_texto(valor, maximo):
    texto = str(valor or "").strip()
    return texto[:maximo] if texto else None


def obtener_sesion_presencia():
    sesion_id = session.get(SESION_CLAVE)
    if not sesion_id:
        sesion_id = secrets.token_urlsafe(32)[:64]
        session[SESION_CLAVE] = sesion_id
    return sesion_id


def registrar_pulso(usuario_id, ruta=None, pagina=None, user_agent=None):
    ahora = _ahora()
    sesion_id = obtener_sesion_presencia()
    presencia = PresenciaUsuario.query.filter_by(sesion_id=sesion_id).first()

    if presencia and presencia.usuario_id != usuario_id:
        db.session.delete(presencia)
        db.session.flush()
        presencia = None

    if not presencia:
        presencia = PresenciaUsuario(
            usuario_id=usuario_id,
            sesion_id=sesion_id,
            iniciado_en=ahora,
            ultimo_pulso_en=ahora,
        )
        db.session.add(presencia)

    presencia.ultimo_pulso_en = ahora
    presencia.ruta = _limite_texto(ruta, 255)
    presencia.pagina = _limite_texto(pagina, 180)
    presencia.user_agent = _limite_texto(user_agent, 255)

    # Limpieza oportunista: una presencia muy antigua ya no aporta información.
    limite_limpieza = ahora - timedelta(days=1)
    PresenciaUsuario.query.filter(
        PresenciaUsuario.ultimo_pulso_en < limite_limpieza,
        PresenciaUsuario.sesion_id != sesion_id,
    ).delete(synchronize_session=False)

    db.session.commit()
    return presencia


def cerrar_presencia(usuario_id=None):
    sesion_id = session.get(SESION_CLAVE)
    if not sesion_id:
        return

    consulta = PresenciaUsuario.query.filter_by(sesion_id=sesion_id)
    if usuario_id is not None:
        consulta = consulta.filter(PresenciaUsuario.usuario_id == usuario_id)
    consulta.delete(synchronize_session=False)
    db.session.commit()
    session.pop(SESION_CLAVE, None)


def listar_usuarios_online():
    ahora = _ahora()
    corte = ahora - timedelta(seconds=_ttl_segundos())
    presencias = (
        PresenciaUsuario.query
        .filter(PresenciaUsuario.ultimo_pulso_en >= corte)
        .order_by(PresenciaUsuario.ultimo_pulso_en.desc())
        .all()
    )

    agrupadas = defaultdict(list)
    for presencia in presencias:
        if presencia.usuario and presencia.usuario.activo:
            agrupadas[presencia.usuario_id].append(presencia)

    usuarios = []
    for sesiones in agrupadas.values():
        sesiones.sort(key=lambda p: p.ultimo_pulso_en, reverse=True)
        reciente = sesiones[0]
        usuario = reciente.usuario
        inicio = min(p.iniciado_en for p in sesiones)
        usuarios.append({
            "id": usuario.id,
            "nombre": usuario.nombre,
            "usuario": usuario.usuario,
            "rol": usuario.etiqueta_rol,
            "sesiones": len(sesiones),
            "pagina": reciente.pagina or "SICODE",
            "ruta": reciente.ruta or "/",
            "iniciado_en": inicio,
            "ultimo_pulso_en": reciente.ultimo_pulso_en,
            "segundos_desde_pulso": max(0, int((ahora - reciente.ultimo_pulso_en).total_seconds())),
        })

    usuarios.sort(key=lambda item: item["ultimo_pulso_en"], reverse=True)
    return usuarios
