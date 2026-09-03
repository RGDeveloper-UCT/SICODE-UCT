(() => {
    if (!document.body.classList.contains('vista-coordinacion-inicio')) return;
    if (document.body.classList.contains('modo-visor')) return;
    const tarjeta = document.querySelector('.tarjeta-registro-coordinacion--anexo');
    if (!tarjeta) return;
    const descripcion = tarjeta.querySelector(':scope > p');
    if (descripcion) descripcion.textContent = 'Catálogo inteligente de anexos documentales con selección guiada, secuencia por SP y revisión de nuevos tipos con NEXO.';
    const subpanel = tarjeta.querySelector('.subpanel-anexos');
    if (!subpanel) return;
    const acciones = document.createElement('div');
    acciones.className = 'acciones-tarjeta-registro';
    const enlace = document.createElement('a');
    enlace.className = 'boton-tarjeta-registro boton-tarjeta-registro-principal';
    enlace.href = '/coordinacion/anexos/nuevo';
    enlace.textContent = 'Registrar anexo';
    enlace.setAttribute('data-sicode-transition-label', 'Abriendo registro de anexos');
    acciones.appendChild(enlace);
    subpanel.replaceWith(acciones);
})();
