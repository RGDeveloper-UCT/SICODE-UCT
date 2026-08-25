import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.analisis_documental_inteligencia import (
    IAAnalisisNoDisponible,
    ocr_pagina_multipase,
    resolver_tesseract,
)
from app.services.analisis_documental_service import DocumentoInvalido, OCRNoDisponible


def _ocr_una_pagina(ruta, indice, idioma, comando, segunda_pasada):
    import pymupdf
    from PIL import Image

    documento = pymupdf.open(str(ruta))
    try:
        pagina = documento.load_page(indice)
        # 1.85x ofrece una base suficiente; el preprocesador OCR reajusta
        # documentos pequeños. alpha=False reduce memoria y tiempo de render.
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(1.85, 1.85), alpha=False)
        modo = "RGB" if pix.n >= 3 else "L"
        imagen = Image.frombytes(modo, (pix.width, pix.height), pix.samples)
        try:
            lectura = ocr_pagina_multipase(
                imagen,
                idioma=idioma,
                tesseract_cmd=comando,
                segunda_pasada=segunda_pasada,
                timeout=55,
            )
        finally:
            imagen.close()
        return indice, lectura
    finally:
        documento.close()


def leer_paginas_rapido(
    ruta,
    *,
    max_paginas=200,
    ocr_habilitado=True,
    ocr_idioma="spa",
    tesseract_cmd=None,
    ocr_segunda_pasada=False,
):
    """Lector compatible con lote_documental_service._leer_paginas.

    Usa PyMuPDF para texto/render y paraleliza únicamente las páginas que
    realmente necesitan OCR. Si PyMuPDF no está disponible, el caller puede
    conservar el lector histórico como fallback.
    """
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PyMuPDF no está instalado para el modo rápido.") from exc

    try:
        documento = pymupdf.open(str(ruta))
    except Exception as exc:
        raise DocumentoInvalido("El archivo no es un PDF válido o está dañado.") from exc

    try:
        if documento.needs_pass:
            if not documento.authenticate(""):
                raise DocumentoInvalido("El PDF está protegido con contraseña.")
        total = documento.page_count
        if total < 1:
            raise DocumentoInvalido("El PDF no contiene páginas.")
        if total > int(max_paginas):
            raise DocumentoInvalido(f"El lote contiene {total} páginas y supera el límite de {max_paginas}.")

        flags = pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_PRESERVE_WHITESPACE
        paginas = []
        pendientes = []
        for indice in range(total):
            pagina = documento.load_page(indice)
            try:
                texto = pagina.get_text("text", flags=flags) or ""
            except Exception:
                texto = ""
            utiles = len(re.sub(r"\W", "", texto, flags=re.UNICODE))
            paginas.append({
                "pagina": indice + 1,
                "texto": texto,
                "origen": "TEXTO_PDF",
                "confianza_ocr": None,
            })
            if utiles < 45:
                pendientes.append(indice)
    finally:
        documento.close()

    paginas_ocr = 0
    if pendientes and ocr_habilitado:
        comando = resolver_tesseract(tesseract_cmd)
        if not comando:
            if all(not p["texto"].strip() for p in paginas):
                raise OCRNoDisponible("El lote parece escaneado y Tesseract no está disponible.")
            return paginas, paginas_ocr

        workers = max(1, min(4, int(os.getenv("DOCUMENT_ANALYSIS_OCR_WORKERS", "2"))))
        workers = min(workers, len(pendientes))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sicode-ocr") as pool:
            futuros = {
                pool.submit(
                    _ocr_una_pagina,
                    ruta,
                    indice,
                    ocr_idioma,
                    comando,
                    ocr_segunda_pasada,
                ): indice
                for indice in pendientes
            }
            for futuro in as_completed(futuros):
                indice = futuros[futuro]
                try:
                    _, lectura = futuro.result()
                except IAAnalisisNoDisponible:
                    continue
                except Exception:
                    continue
                if (lectura.get("texto") or "").strip():
                    paginas[indice]["texto"] = lectura["texto"]
                    paginas[indice]["origen"] = "OCR_PARALELO"
                    paginas[indice]["confianza_ocr"] = int(round(float(lectura.get("confianza") or 0)))
                    paginas_ocr += 1

    return paginas, paginas_ocr
