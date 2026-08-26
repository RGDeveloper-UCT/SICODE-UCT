(() => {
    const overlay = document.querySelector("[data-sicode-transicion]");
    if (!overlay) {
        return;
    }

    const subtitulo = overlay.querySelector("[data-sicode-transicion-subtitulo]");
    const usuarioId = document.body.dataset.sicodeUser || "anonimo";
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let navegacionProgramada = false;

    const mostrar = (mensaje) => {
        if (subtitulo) {
            subtitulo.textContent = mensaje || "Cargando módulo";
        }
        overlay.classList.add("sicode-transicion--activa");
        overlay.setAttribute("aria-hidden", "false");
    };

    const ocultar = () => {
        overlay.classList.remove("sicode-transicion--activa");
        overlay.setAttribute("aria-hidden", "true");
    };

    const claveBienvenida = `sicode-bienvenida-${usuarioId}`;
    try {
        if (!sessionStorage.getItem(claveBienvenida)) {
            sessionStorage.setItem(claveBienvenida, "1");
            mostrar("Bienvenido al sistema");
            window.setTimeout(ocultar, reduceMotion ? 280 : 850);
        }
    } catch (_error) {
        // La navegación sigue funcionando aunque el navegador limite sessionStorage.
    }

    const enlaceValido = (enlace, evento) => {
        if (
            evento.defaultPrevented ||
            evento.button !== 0 ||
            evento.metaKey ||
            evento.ctrlKey ||
            evento.shiftKey ||
            evento.altKey
        ) {
            return false;
        }

        if (
            enlace.hasAttribute("download") ||
            enlace.dataset.noTransition !== undefined ||
            enlace.getAttribute("target") === "_blank"
        ) {
            return false;
        }

        const href = enlace.getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:") || href.startsWith("javascript:")) {
            return false;
        }

        const destino = new URL(enlace.href, window.location.href);
        if (destino.origin !== window.location.origin) {
            return false;
        }

        const soloAncla =
            destino.pathname === window.location.pathname &&
            destino.search === window.location.search &&
            destino.hash;

        return !soloAncla;
    };

    document.addEventListener("click", (evento) => {
        if (navegacionProgramada || !(evento.target instanceof Element)) {
            return;
        }

        const enlace = evento.target.closest("a[href]");
        if (!enlace || !enlaceValido(enlace, evento)) {
            return;
        }

        const destino = new URL(enlace.href, window.location.href);
        const esMenuPrincipal = Boolean(enlace.closest(".topbar nav"));
        const nombreDestino = enlace.textContent.replace(/\s+/g, " ").trim();
        const mensaje = esMenuPrincipal && nombreDestino
            ? `Abriendo ${nombreDestino}`
            : "Cargando módulo";

        if (destino.pathname.toLowerCase().includes("logout")) {
            try {
                sessionStorage.removeItem(claveBienvenida);
            } catch (_error) {
                // No bloquea el cierre de sesión.
            }
        }

        evento.preventDefault();
        navegacionProgramada = true;
        mostrar(mensaje);

        window.setTimeout(() => {
            window.location.assign(destino.href);
        }, reduceMotion ? 70 : 260);
    });

    window.addEventListener("pageshow", (evento) => {
        if (evento.persisted) {
            navegacionProgramada = false;
            ocultar();
        }
    });
})();

/* Carrete horizontal de tarjetas en Coordinación.
   Conserva todas las opciones en una sola fila y usa desplazamiento interpolado
   para que flechas, rueda, teclado y arrastre se sientan suaves y predecibles. */
(() => {
    const track = document.querySelector(".vista-coordinacion-inicio .grid-registros-coordinacion");
    const header = document.querySelector(".vista-coordinacion-inicio .encabezado-registros-coordinacion");
    if (!track || !header) {
        return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const style = document.createElement("style");
    style.textContent = `
        .vista-coordinacion-inicio .encabezado-registros-coordinacion {
            align-items: center;
        }
        .vista-coordinacion-inicio .coord-carrete-meta {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 9px;
            min-width: 0;
        }
        .vista-coordinacion-inicio .coord-carrete-meta > span {
            white-space: nowrap;
        }
        .vista-coordinacion-inicio .coord-carrete-controles {
            display: inline-flex;
            gap: 6px;
            flex: 0 0 auto;
        }
        .vista-coordinacion-inicio .coord-carrete-boton {
            width: 35px;
            height: 31px;
            display: inline-grid;
            place-items: center;
            padding: 0;
            border: 1px solid #cbd8e8;
            border-radius: 9px;
            background: #f8fbff;
            color: #173a66;
            font: 900 19px/1 system-ui, sans-serif;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(23, 35, 60, .06);
            transition: background .18s ease, border-color .18s ease, transform .18s ease, box-shadow .18s ease, opacity .18s ease;
        }
        .vista-coordinacion-inicio .coord-carrete-boton:hover:not(:disabled) {
            background: #eaf3fd;
            border-color: #8eb0d5;
            box-shadow: 0 4px 10px rgba(23, 58, 102, .10);
            transform: translateY(-1px);
        }
        .vista-coordinacion-inicio .coord-carrete-boton:active:not(:disabled) {
            transform: translateY(0) scale(.96);
        }
        .vista-coordinacion-inicio .coord-carrete-boton:disabled {
            opacity: .30;
            cursor: default;
            box-shadow: none;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
            display: flex !important;
            flex: 1 1 auto;
            flex-flow: row nowrap !important;
            align-items: stretch;
            gap: 12px;
            min-width: 0;
            min-height: 0;
            overflow-x: auto;
            overflow-y: hidden;
            scroll-snap-type: x proximity;
            scroll-behavior: auto;
            overscroll-behavior-inline: contain;
            scrollbar-width: none;
            -ms-overflow-style: none;
            padding: 2px 2px 7px;
            cursor: grab;
            touch-action: pan-x pan-y;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track::-webkit-scrollbar {
            display: none;
            width: 0;
            height: 0;
        }
        .vista-coordinacion-inicio .coord-carrete-track > .tarjeta-registro-coordinacion {
            flex: 0 0 calc((100% - 36px) / 4);
            width: auto;
            min-width: 0;
            height: 100%;
            scroll-snap-align: start;
            scroll-snap-stop: normal;
        }
        .vista-coordinacion-inicio .coord-carrete-track.coord-carrete-arrastrando {
            cursor: grabbing;
            scroll-snap-type: none;
            user-select: none;
        }
        .vista-coordinacion-inicio .coord-carrete-track.coord-carrete-arrastrando * {
            user-select: none;
        }
        @media (max-width: 1600px) {
            .vista-coordinacion-inicio .coord-carrete-track > .tarjeta-registro-coordinacion {
                flex-basis: calc((100% - 24px) / 3);
            }
        }
        @media (max-width: 1180px) {
            .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
                min-height: 255px;
            }
            .vista-coordinacion-inicio .coord-carrete-track > .tarjeta-registro-coordinacion {
                flex-basis: calc((100% - 12px) / 2);
                height: auto;
            }
            .vista-coordinacion-inicio .coord-carrete-meta > span {
                display: none;
            }
        }
        @media (max-width: 760px) {
            .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
                min-height: 245px;
            }
            .vista-coordinacion-inicio .coord-carrete-track > .tarjeta-registro-coordinacion {
                flex-basis: 88%;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .vista-coordinacion-inicio .coord-carrete-boton {
                transition: none;
            }
        }
    `;
    document.head.appendChild(style);

    track.classList.add("coord-carrete-track");
    track.tabIndex = 0;
    track.setAttribute("role", "region");
    track.setAttribute("aria-label", "Tipos de registro de Coordinación en una sola fila. Use las flechas para desplazarse.");

    const textoAyuda = header.querySelector(":scope > span");
    const meta = document.createElement("div");
    meta.className = "coord-carrete-meta";
    if (textoAyuda) {
        meta.appendChild(textoAyuda);
    }

    const controles = document.createElement("div");
    controles.className = "coord-carrete-controles";
    controles.setAttribute("aria-label", "Mover carrete de registros");

    const crearBoton = (direccion, etiqueta, simbolo) => {
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "coord-carrete-boton";
        boton.dataset.direccion = direccion;
        boton.setAttribute("aria-label", etiqueta);
        boton.title = etiqueta;
        boton.textContent = simbolo;
        return boton;
    };

    const anterior = crearBoton("anterior", "Ver registros anteriores", "‹");
    const siguiente = crearBoton("siguiente", "Ver más registros", "›");
    controles.append(anterior, siguiente);
    meta.appendChild(controles);
    header.appendChild(meta);

    let animacionId = null;
    let destinoRueda = track.scrollLeft;
    let temporizadorRueda = null;
    let frameEstado = null;

    const limitar = (valor, minimo, maximo) => Math.min(maximo, Math.max(minimo, valor));
    const easeInOutCubic = (t) => t < .5
        ? 4 * t * t * t
        : 1 - Math.pow(-2 * t + 2, 3) / 2;

    const maxScroll = () => Math.max(0, track.scrollWidth - track.clientWidth);

    const cancelarAnimacion = () => {
        if (animacionId !== null) {
            window.cancelAnimationFrame(animacionId);
            animacionId = null;
        }
    };

    const actualizarControles = () => {
        frameEstado = null;
        const maximo = maxScroll();
        anterior.disabled = track.scrollLeft <= 2;
        siguiente.disabled = maximo <= 2 || track.scrollLeft >= maximo - 2;
    };

    const programarActualizacion = () => {
        if (frameEstado === null) {
            frameEstado = window.requestAnimationFrame(actualizarControles);
        }
    };

    const moverA = (destino, duracionBase = 480) => {
        const inicio = track.scrollLeft;
        const final = limitar(destino, 0, maxScroll());
        const distancia = final - inicio;

        destinoRueda = final;
        cancelarAnimacion();

        if (Math.abs(distancia) < 1 || reduceMotion) {
            track.scrollLeft = final;
            programarActualizacion();
            return;
        }

        const inicioTiempo = performance.now();
        const duracion = limitar(Math.abs(distancia) * .55, 300, duracionBase);

        const animar = (ahora) => {
            const progreso = limitar((ahora - inicioTiempo) / duracion, 0, 1);
            track.scrollLeft = inicio + distancia * easeInOutCubic(progreso);

            if (progreso < 1) {
                animacionId = window.requestAnimationFrame(animar);
            } else {
                animacionId = null;
                track.scrollLeft = final;
                programarActualizacion();
            }
        };

        animacionId = window.requestAnimationFrame(animar);
    };

    const medidaTarjeta = () => {
        const tarjeta = track.querySelector(":scope > .tarjeta-registro-coordinacion");
        if (!tarjeta) {
            return Math.max(track.clientWidth * .72, 260);
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

    const desplazar = (sentido) => {
        destinoRueda = track.scrollLeft;
        moverA(track.scrollLeft + sentido * paso(), 560);
    };

    anterior.addEventListener("click", () => desplazar(-1));
    siguiente.addEventListener("click", () => desplazar(1));

    track.addEventListener("scroll", programarActualizacion, { passive: true });
    window.addEventListener("resize", () => {
        destinoRueda = track.scrollLeft;
        programarActualizacion();
    }, { passive: true });

    track.addEventListener("wheel", (evento) => {
        const maximo = maxScroll();
        if (maximo <= 2 || Math.abs(evento.deltaY) <= Math.abs(evento.deltaX)) {
            return;
        }

        const vaDerecha = evento.deltaY > 0;
        const puedeMover = vaDerecha ? track.scrollLeft < maximo - 2 : track.scrollLeft > 2;
        if (!puedeMover) {
            return;
        }

        evento.preventDefault();
        destinoRueda = limitar(destinoRueda + evento.deltaY * 1.45, 0, maximo);
        moverA(destinoRueda, 360);

        window.clearTimeout(temporizadorRueda);
        temporizadorRueda = window.setTimeout(() => {
            destinoRueda = track.scrollLeft;
        }, 420);
    }, { passive: false });

    track.addEventListener("keydown", (evento) => {
        if (evento.key === "ArrowLeft") {
            evento.preventDefault();
            desplazar(-1);
        } else if (evento.key === "ArrowRight") {
            evento.preventDefault();
            desplazar(1);
        } else if (evento.key === "Home") {
            evento.preventDefault();
            moverA(0, 520);
        } else if (evento.key === "End") {
            evento.preventDefault();
            moverA(maxScroll(), 520);
        }
    });

    let arrastrando = false;
    let punteroId = null;
    let inicioX = 0;
    let inicioScroll = 0;
    let huboArrastre = false;
    let bloquearClick = false;

    track.addEventListener("pointerdown", (evento) => {
        if (evento.pointerType !== "mouse" || evento.button !== 0) {
            return;
        }

        cancelarAnimacion();
        arrastrando = true;
        punteroId = evento.pointerId;
        inicioX = evento.clientX;
        inicioScroll = track.scrollLeft;
        huboArrastre = false;
        track.classList.add("coord-carrete-arrastrando");
        track.setPointerCapture(evento.pointerId);
    });

    track.addEventListener("pointermove", (evento) => {
        if (!arrastrando || evento.pointerId !== punteroId) {
            return;
        }

        const delta = evento.clientX - inicioX;
        if (Math.abs(delta) > 6) {
            huboArrastre = true;
        }
        track.scrollLeft = limitar(inicioScroll - delta, 0, maxScroll());
        destinoRueda = track.scrollLeft;
    });

    const terminarArrastre = (evento) => {
        if (!arrastrando || evento.pointerId !== punteroId) {
            return;
        }

        arrastrando = false;
        track.classList.remove("coord-carrete-arrastrando");
        if (track.hasPointerCapture(evento.pointerId)) {
            track.releasePointerCapture(evento.pointerId);
        }
        punteroId = null;

        if (huboArrastre) {
            bloquearClick = true;
            window.setTimeout(() => {
                bloquearClick = false;
            }, 0);
        }
        programarActualizacion();
    };

    track.addEventListener("pointerup", terminarArrastre);
    track.addEventListener("pointercancel", terminarArrastre);

    track.addEventListener("click", (evento) => {
        if (!bloquearClick) {
            return;
        }
        evento.preventDefault();
        evento.stopPropagation();
    }, true);

    actualizarControles();
})();
