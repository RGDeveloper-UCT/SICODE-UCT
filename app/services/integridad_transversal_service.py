"""Correcciones transversales de integridad para flujos históricos de SICODE.

Este módulo concentra reglas que deben ser idénticas en análisis individual,
lotes documentales y SICODE.IA. Se instala una sola vez al cargar las rutas para
evitar que cada flujo vuelva a implementar una definición distinta de foliación.
"""

from __future__ import annotations

import importlib
import os

from flask import request

from app import db
from app.models.documento_expediente import DocumentoExpediente


def _limpiar(valor, maximo=None):
    texto = str(valor or "").strip()
    if not texto:
        return None
    return texto[:maximo] if maximo else texto


def _solapado_principal(expediente_id, inicio, fin):
    """Busca traslapes solo dentro de la foliación del cuerpo principal."""
    return (
        DocumentoExpediente.query
        .filter_by(expediente_id=expediente_id, activo=True, es_anexo=False)
        .filter(
            DocumentoExpediente.folio_inicio <= fin,
            DocumentoExpediente.folio_fin >= inicio,
        )
        .first()
    )


def _crear_indice_anexo_analisis(expediente, datos, validacion):
    """Índice desde análisis individual: cada anexo tiene foliación propia."""
    if request.form.get("crear_indice") != "1" or expediente is None:
        return None, None

    inicio, fin = validacion["folio_inicio"], validacion["folio_fin"]
    if inicio is None or fin is None:
        return None, "No se creó índice documental porque no hay un rango de folios confirmado."

    titulo = _limpiar(datos.get("titulo_anexo"), 180) or "Anexo"
    numero = _limpiar(datos.get("numero_anexo"), 50)
    nombre = f"Anexo {numero} - {titulo}" if numero else titulo
    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=nombre[:180],
        tipo_documento="Anexo",
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision="Pendiente de revisión",
        es_anexo=True,
        observaciones="Incorporado desde Análisis documental asistido; validado por usuario.",
        activo=True,
    )
    db.session.add(documento)
    db.session.flush()
    return documento, None


def _crear_indice_lote(expediente, tipo, datos, inicio, fin):
    """Índice desde lote: anexos independientes; cuerpo principal sí valida solape."""
    if not expediente or inicio is None or fin is None:
        return None, "No se agregó al índice documental porque falta SP o rango de folios confirmado."

    if tipo != "ANEXO":
        solapado = _solapado_principal(expediente.id, inicio, fin)
        if solapado:
            return None, (
                f"El rango {inicio}-{fin} se cruza con {solapado.nombre_documento}; "
                "no se agregó automáticamente al índice."
            )

    if tipo == "ANEXO":
        numero = _limpiar(datos.get("numero_anexo"), 50)
        titulo = _limpiar(datos.get("titulo_anexo"), 180) or "Anexo"
        nombre = f"Anexo {numero} - {titulo}" if numero else titulo
    elif tipo == "DPI":
        nombre = "DPI identificado (datos personales no almacenados)"
    else:
        nombre = _limpiar(datos.get("nombre_documento"), 180)
        if not nombre:
            numero = _limpiar(datos.get("numero_documento"), 100)
            nombre = f"{tipo} {numero}" if numero else tipo.title()

    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=nombre[:180],
        tipo_documento=tipo.title()[:80],
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision="Pendiente de revisión",
        es_anexo=(tipo == "ANEXO"),
        observaciones="Clasificado desde lote documental; PDF temporal eliminado tras el análisis.",
        activo=True,
    )
    db.session.add(documento)
    db.session.flush()
    return documento, None


def _crear_indice_sicode_ia(expediente, tipo, datos, inicio, fin):
    """Índice definitivo desde SICODE.IA con la misma regla canónica."""
    if not expediente or inicio is None or fin is None:
        return None

    if tipo != "ANEXO" and _solapado_principal(expediente.id, inicio, fin):
        return None

    numero = _limpiar(datos.get("numero_anexo"), 50)
    titulo = _limpiar(datos.get("titulo_anexo"), 180)
    nombre = (
        f"Anexo {numero} - {titulo}"
        if tipo == "ANEXO" and numero
        else (
            titulo
            if tipo == "ANEXO" and titulo
            else (
                _limpiar(datos.get("nombre_documento"), 180)
                or _limpiar(datos.get("numero_documento"), 120)
                or tipo.title()
            )
        )
    )
    documento = DocumentoExpediente(
        expediente_id=expediente.id,
        nombre_documento=nombre[:180],
        tipo_documento=tipo.title()[:80],
        folio_inicio=inicio,
        folio_fin=fin,
        total_folios=fin - inicio + 1,
        estado_revision="Pendiente de revisión",
        es_anexo=(tipo == "ANEXO"),
        observaciones="Carga definitiva desde SICODE.IA tras doble verificación humana.",
        activo=True,
    )
    db.session.add(documento)
    db.session.flush()
    return documento


def _asegurar_fchmod_compatible():
    """Provee un no-op solo en plataformas que no exponen os.fchmod (Windows)."""
    if hasattr(os, "fchmod"):
        return

    def _fchmod_no_disponible(_descriptor, _modo):
        return None

    os.fchmod = _fchmod_no_disponible  # type: ignore[attr-defined]


def instalar_integridad_transversal():
    """Instala una sola definición para los tres flujos asistidos históricos."""
    _asegurar_fchmod_compatible()

    analisis = importlib.import_module("app.routes.analisis_documental")
    lote = importlib.import_module("app.routes.lote_documental")
    sicode_ia = importlib.import_module("app.routes.sicode_ia")

    analisis._crear_indice_anexo = _crear_indice_anexo_analisis
    lote._crear_indice = _crear_indice_lote
    sicode_ia._crear_indice = _crear_indice_sicode_ia
