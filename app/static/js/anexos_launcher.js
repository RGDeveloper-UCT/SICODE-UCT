(() => {
    if (!document.body.classList.contains('vista-coordinacion-inicio')) return;
    if (document.body.classList.contains('modo-visor')) return;

    const destino = '/coordinacion/anexos/nuevo';
    const tarjeta = document.querySelector('.tarjeta-registro-coordinacion--anexo');
    if (!tarjeta) return;

    const descripcion = tarjeta.querySelector(':scope > p');
    if (descripcion) {
        descripcion.textContent = 'Catálogo inteligente de anexos documentales con selección guiada, secuencia por SP y revisión de nuevos tipos con NEXO.';
    }

    const abrirRegistro = (evento) => {
        if (evento) {
            evento.preventDefault();
            evento.stopPropagation();
            if (typeof evento.stopImmediatePropagation === 'function') {
                evento.stopImmediatePropagation();
            }
        }
        window.location.href = destino;
    };

    const subpanel = tarjeta.querySelector('.subpanel-anexos');
    if (subpanel) {
        const acciones = document.createElement('div');
        acciones.className = 'acciones-tarjeta-registro';

        const enlace = document.createElement('a');
        enlace.className = 'boton-tarjeta-registro boton-tarjeta-registro-principal';
        enlace.href = destino;
        enlace.textContent = 'Registrar anexo';
        enlace.draggable = false;
        enlace.style.cursor = 'pointer';
        enlace.style.pointerEvents = 'auto';
        enlace.style.position = 'relative';
        enlace.style.zIndex = '50';

        // El inicio de Coordinación usa un carrusel horizontal con eventos de
        // puntero. Este botón se crea dinámicamente después de inicializar dicho
        // carrusel, por lo que debemos detener el pointerdown aquí para que nunca
        // se interprete como gesto de arrastre.
        enlace.addEventListener('pointerdown', (evento) => {
            evento.stopPropagation();
            evento.stopImmediatePropagation();
        }, true);
        enlace.addEventListener('mousedown', (evento) => {
            evento.stopPropagation();
            evento.stopImmediatePropagation();
        }, true);
        enlace.addEventListener('dragstart', (evento) => evento.preventDefault(), true);
        enlace.addEventListener('click', abrirRegistro, true);

        acciones.appendChild(enlace);
        subpanel.replaceWith(acciones);
    }

    // Respaldo defensivo para HTML cacheado: cualquier activador anterior de
    // Anexos se transforma en navegación directa, incluso si el carrusel intenta
    // capturar el puntero.
    tarjeta.addEventListener('pointerdown', (evento) => {
        const objetivo = evento.target.closest('.boton-tarjeta-registro-principal, .subpanel-anexos summary');
        if (!objetivo || !tarjeta.contains(objetivo)) return;
        evento.stopPropagation();
        evento.stopImmediatePropagation();
    }, true);

    tarjeta.addEventListener('click', (evento) => {
        const objetivo = evento.target.closest('.boton-tarjeta-registro-principal, .subpanel-anexos summary');
        if (!objetivo || !tarjeta.contains(objetivo)) return;
        abrirRegistro(evento);
    }, true);
})();
