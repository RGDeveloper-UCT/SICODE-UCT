(() => {
    const input = document.querySelector('[data-pdf-input]');
    const nombre = document.querySelector('[data-pdf-name]');
    if (input && nombre) {
        input.addEventListener('change', () => {
            const archivo = input.files && input.files[0];
            if (!archivo) {
                nombre.textContent = 'Ningún archivo seleccionado';
                return;
            }
            const mb = archivo.size / (1024 * 1024);
            nombre.textContent = `${archivo.name} · ${mb.toFixed(1)} MB`;
        });
    }

    const formularioAnalisis = document.querySelector('[data-analisis-form]');
    const loader = document.querySelector('[data-analisis-loader]');
    if (formularioAnalisis && loader) {
        formularioAnalisis.addEventListener('submit', () => {
            loader.hidden = false;
            document.body.style.overflow = 'hidden';

            const progreso = loader.querySelector('[data-loader-progress]');
            const mensaje = loader.querySelector('[data-loader-message]');
            const iaActiva = loader.dataset.iaEnabled === '1';
            const etapas = ['pdf', 'ocr', 'reglas', 'ia', 'sicode'];
            const metas = [12, 38, 58, 78, 92];
            const mensajes = {
                pdf: 'Preparando el PDF en almacenamiento temporal…',
                ocr: 'Leyendo páginas y reforzando las que necesitan OCR…',
                reglas: 'Buscando SP, RC, providencias, anexos y foliación…',
                ia: iaActiva ? 'La IA local está interpretando posibles errores del OCR…' : 'La IA está deshabilitada; continuando con reglas determinísticas…',
                sicode: 'Comparando la propuesta con la información existente en SICODE…',
            };

            let indice = 0;
            const pintar = () => {
                etapas.forEach((clave, posicion) => {
                    const elemento = loader.querySelector(`[data-loader-step="${clave}"]`);
                    if (!elemento) return;
                    elemento.classList.toggle('es-completa', posicion < indice);
                    elemento.classList.toggle('es-activa', posicion === indice);
                });
                if (progreso) progreso.style.width = `${metas[Math.min(indice, metas.length - 1)]}%`;
                if (mensaje) mensaje.textContent = mensajes[etapas[indice]];
            };

            pintar();
            const intervalo = window.setInterval(() => {
                if (indice < etapas.length - 1) {
                    indice += 1;
                    pintar();
                } else {
                    if (mensaje) mensaje.textContent = 'Finalizando cálculos de confianza y preparando la revisión…';
                    if (progreso) progreso.style.width = '94%';
                    window.clearInterval(intervalo);
                }
            }, 1800);
        });
    }

    const selectorTipo = document.querySelector('[data-tipo-registro]');
    const paneles = Array.from(document.querySelectorAll('[data-tipo-panel]'));

    const actualizarPaneles = () => {
        if (!selectorTipo) return;
        const tipo = selectorTipo.value;
        paneles.forEach((panel) => {
            const tipos = (panel.dataset.tipoPanel || '').split(/\s+/).filter(Boolean);
            const visible = tipos.includes(tipo);
            panel.hidden = !visible;
            panel.querySelectorAll('input, select, textarea').forEach((campo) => {
                if (campo.dataset.requiredOriginal === '1') {
                    campo.required = visible;
                }
            });
        });
    };

    paneles.forEach((panel) => {
        panel.querySelectorAll('[required]').forEach((campo) => {
            campo.dataset.requiredOriginal = '1';
        });
    });

    if (selectorTipo) {
        selectorTipo.addEventListener('change', actualizarPaneles);
        actualizarPaneles();
    }

    const barras = Array.from(document.querySelectorAll('[data-confidence-bar]'));
    const anillo = document.querySelector('[data-quality-ring]');
    if (barras.length || anillo) {
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                barras.forEach((barra) => {
                    const porcentaje = Math.max(0, Math.min(100, Number(barra.dataset.confidence || 0)));
                    barra.style.width = `${porcentaje}%`;
                });
                if (anillo) anillo.classList.add('es-visible');
            });
        });
    }
})();
