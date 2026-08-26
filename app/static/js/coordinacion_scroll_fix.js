(() => {
    const track = document.querySelector(".vista-coordinacion-inicio .grid-registros-coordinacion");
    if (!track) {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const limitar = (valor, minimo, maximo) => Math.min(maximo, Math.max(minimo, valor));
    const maxScroll = () => Math.max(0, track.scrollWidth - track.clientWidth);

    let animacionId = null;
    let destinoGestual = track.scrollLeft;

    const easeInOutQuint = (t) => t < .5
        ? 16 * t * t * t * t * t
        : 1 - Math.pow(-2 * t + 2, 5) / 2;

    const cancelarAnimacion = () => {
        if (animacionId !== null) {
            window.cancelAnimationFrame(animacionId);
            animacionId = null;
        }
    };

    const moverSuaveA = (destino, duracionBase = 620) => {
        const inicio = track.scrollLeft;
        const final = limitar(destino, 0, maxScroll());
        const distancia = final - inicio;
        destinoGestual = final;

        cancelarAnimacion();

        if (reduceMotion || Math.abs(distancia) < 1) {
            track.scrollLeft = final;
            return;
        }

        const inicioTiempo = performance.now();
        const duracion = limitar(Math.abs(distancia) * .72, 360, duracionBase);

        const animar = (ahora) => {
            const progreso = limitar((ahora - inicioTiempo) / duracion, 0, 1);
            track.scrollLeft = inicio + distancia * easeInOutQuint(progreso);

            if (progreso < 1) {
                animacionId = window.requestAnimationFrame(animar);
                return;
            }

            animacionId = null;
            track.scrollLeft = final;
        };

        animacionId = window.requestAnimationFrame(animar);
    };

    const medidaTarjeta = () => {
        const tarjeta = track.querySelector(":scope > .tarjeta-registro-coordinacion");
        if (!tarjeta) {
            return Math.max(track.clientWidth * .7, 260);
        }
        const estilos = window.getComputedStyle(track);
        const gap = Number.parseFloat(estilos.columnGap || estilos.gap || "12") || 12;
        return tarjeta.getBoundingClientRect().width + gap;
    };

    const paso = () => {
        const medida = medidaTarjeta();
        const visibles = Math.max(1, Math.floor((track.clientWidth + 4) / medida));
        return medida * Math.max(1, visibles - 1);
    };

    /*
     * Los botones de registro son controles interactivos, no zonas de arrastre.
     * Detener pointerdown en el propio control evita que el listener de arrastre
     * del carrete capture el puntero y termine anulando la navegación del enlace.
     */
    track.querySelectorAll("a, button, input, select, textarea, label").forEach((control) => {
        control.addEventListener("pointerdown", (evento) => {
            evento.stopPropagation();
        });
    });

    /*
     * Flechas del carrete: interceptamos el click antes del listener anterior y
     * usamos una curva quintica más progresiva para un movimiento menos brusco.
     */
    track.parentElement?.querySelectorAll(".coord-carrete-boton").forEach((boton) => {
        boton.addEventListener("click", (evento) => {
            evento.preventDefault();
            evento.stopImmediatePropagation();

            const sentido = boton.dataset.direccion === "anterior" ? -1 : 1;
            moverSuaveA(track.scrollLeft + sentido * paso(), 700);
        }, { capture: true });
    });

    /* Teclado con la misma animación fluida de las flechas. */
    track.addEventListener("keydown", (evento) => {
        let destino = null;

        if (evento.key === "ArrowLeft") {
            destino = track.scrollLeft - paso();
        } else if (evento.key === "ArrowRight") {
            destino = track.scrollLeft + paso();
        } else if (evento.key === "Home") {
            destino = 0;
        } else if (evento.key === "End") {
            destino = maxScroll();
        }

        if (destino === null) {
            return;
        }

        evento.preventDefault();
        evento.stopImmediatePropagation();
        moverSuaveA(destino, 700);
    }, { capture: true });

    /*
     * La rueda vertical pertenece a la página. Solo un gesto horizontal real,
     * o Shift + rueda, mueve el carrete. El desplazamiento horizontal también
     * utiliza requestAnimationFrame para evitar saltos entre eventos consecutivos.
     */
    track.addEventListener("wheel", (evento) => {
        const horizontalReal = Math.abs(evento.deltaX) > Math.abs(evento.deltaY);
        const horizontalConShift = evento.shiftKey && Math.abs(evento.deltaY) > 0;

        if (!horizontalReal && !horizontalConShift) {
            evento.stopImmediatePropagation();
            return;
        }

        const maximo = maxScroll();
        if (maximo <= 2) {
            evento.stopImmediatePropagation();
            return;
        }

        const delta = horizontalReal ? evento.deltaX : evento.deltaY;
        evento.preventDefault();
        evento.stopImmediatePropagation();

        destinoGestual = limitar(destinoGestual + delta * 1.25, 0, maximo);
        moverSuaveA(destinoGestual, 420);
    }, { capture: true, passive: false });

    track.addEventListener("pointerdown", (evento) => {
        if (evento.target instanceof Element && evento.target.closest("a, button, input, select, textarea, label")) {
            cancelarAnimacion();
            destinoGestual = track.scrollLeft;
            return;
        }

        destinoGestual = track.scrollLeft;
    }, { capture: true });

    track.addEventListener("scroll", () => {
        if (animacionId === null) {
            destinoGestual = track.scrollLeft;
        }
    }, { passive: true });
})();
