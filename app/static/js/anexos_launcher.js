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
        }
        window.location.assign(destino);
    };

    const subpanel = tarjeta.querySelector('.subpanel-anexos');
    if (subpanel) {
        const acciones = document.createElement('div');
        acciones.className = 'acciones-tarjeta-registro';

        const enlace = document.createElement('a');
        enlace.className = 'boton-tarjeta-registro boton-tarjeta-registro-principal';
        enlace.href = destino;
        enlace.textContent = 'Registrar anexo';
        enlace.addEventListener('click', abrirRegistro, true);

        acciones.appendChild(enlace);
        subpanel.replaceWith(acciones);
    }

    // Respaldo defensivo: si el navegador conserva HTML anterior o algún script
    // vuelve a dibujar el botón original, cualquier clic en la acción principal
    // de la tarjeta de Anexos abre directamente el nuevo módulo.
    tarjeta.addEventListener('click', (evento) => {
        const objetivo = evento.target.closest('.boton-tarjeta-registro-principal, .subpanel-anexos summary');
        if (!objetivo || !tarjeta.contains(objetivo)) return;
        abrirRegistro(evento);
    }, true);
})();
