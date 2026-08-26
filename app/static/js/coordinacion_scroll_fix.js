(() => {
    const track = document.querySelector(".vista-coordinacion-inicio .grid-registros-coordinacion");
    if (!track) {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const limitar = (valor, minimo, maximo) => Math.min(maximo, Math.max(minimo, valor));

    /*
     * transiciones.js mantiene el carrete horizontal y sus flechas. Este listener
     * se registra en fase de captura para que la rueda vertical vuelva a pertenecer
     * a la página. Solo un gesto horizontal real, o Shift + rueda, mueve el carrete.
     */
    track.addEventListener("wheel", (evento) => {
        const horizontalReal = Math.abs(evento.deltaX) > Math.abs(evento.deltaY);
        const horizontalConShift = evento.shiftKey && Math.abs(evento.deltaY) > 0;

        if (!horizontalReal && !horizontalConShift) {
            /* Evita que el listener antiguo convierta la rueda vertical en
               desplazamiento horizontal, pero conserva la acción por defecto:
               el navegador desplaza verticalmente el documento. */
            evento.stopImmediatePropagation();
            return;
        }

        const delta = horizontalReal ? evento.deltaX : evento.deltaY;
        const maximo = Math.max(0, track.scrollWidth - track.clientWidth);
        if (maximo <= 2) {
            evento.stopImmediatePropagation();
            return;
        }

        const destino = limitar(track.scrollLeft + delta * 1.35, 0, maximo);
        evento.preventDefault();
        evento.stopImmediatePropagation();
        track.scrollTo({
            left: destino,
            behavior: reduceMotion ? "auto" : "smooth",
        });
    }, { capture: true, passive: false });
})();
