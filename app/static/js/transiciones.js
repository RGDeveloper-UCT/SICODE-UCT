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
   Mantiene dos filas visibles y desplaza las columnas lateralmente para evitar
   que tipos adicionales (por ejemplo Remisión) queden fuera del viewport. */
(() => {
    const track = document.querySelector(".vista-coordinacion-inicio .grid-registros-coordinacion");
    const header = document.querySelector(".vista-coordinacion-inicio .encabezado-registros-coordinacion");
    if (!track || !header) {
        return;
    }

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
            gap: 5px;
            flex: 0 0 auto;
        }
        .vista-coordinacion-inicio .coord-carrete-boton {
            width: 33px;
            height: 30px;
            display: inline-grid;
            place-items: center;
            padding: 0;
            border: 1px solid #cbd8e8;
            border-radius: 8px;
            background: #f7faff;
            color: #173a66;
            font: 900 18px/1 system-ui, sans-serif;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(23, 35, 60, .06);
            transition: background .14s ease, border-color .14s ease, transform .14s ease, opacity .14s ease;
        }
        .vista-coordinacion-inicio .coord-carrete-boton:hover:not(:disabled) {
            background: #e9f2fd;
            border-color: #8eb0d5;
            transform: translateY(-1px);
        }
        .vista-coordinacion-inicio .coord-carrete-boton:disabled {
            opacity: .34;
            cursor: default;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
            display: grid;
            grid-template-columns: none !important;
            grid-template-rows: repeat(2, minmax(0, 1fr)) !important;
            grid-auto-flow: column;
            grid-auto-columns: calc((100% - 30px) / 4);
            gap: 10px;
            overflow-x: auto;
            overflow-y: hidden;
            scroll-snap-type: x mandatory;
            scroll-behavior: smooth;
            overscroll-behavior-inline: contain;
            scrollbar-width: thin;
            scrollbar-color: #9fb5cf #edf3fa;
            padding-bottom: 5px;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track::-webkit-scrollbar {
            height: 7px;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track::-webkit-scrollbar-track {
            background: #edf3fa;
            border-radius: 999px;
        }
        .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track::-webkit-scrollbar-thumb {
            background: #9fb5cf;
            border-radius: 999px;
        }
        .vista-coordinacion-inicio .coord-carrete-track > .tarjeta-registro-coordinacion {
            scroll-snap-align: start;
            min-width: 0;
        }
        @media (max-width: 1600px) {
            .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
                grid-auto-columns: calc((100% - 20px) / 3);
            }
        }
        @media (max-width: 1180px) {
            .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
                grid-auto-columns: calc((100% - 10px) / 2);
            }
            .vista-coordinacion-inicio .coord-carrete-meta > span {
                display: none;
            }
        }
        @media (max-width: 760px) {
            .vista-coordinacion-inicio .grid-registros-coordinacion.coord-carrete-track {
                grid-auto-columns: 88%;
            }
        }
    `;
    document.head.appendChild(style);

    track.classList.add("coord-carrete-track");
    track.tabIndex = 0;
    track.setAttribute("role", "region");
    track.setAttribute("aria-label", "Tipos de registro de Coordinación. Use las flechas para desplazarse.");

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

    const paso = () => Math.max(track.clientWidth * 0.82, 260);
    const desplazar = (sentido) => {
        track.scrollBy({ left: sentido * paso(), behavior: "smooth" });
    };

    anterior.addEventListener("click", () => desplazar(-1));
    siguiente.addEventListener("click", () => desplazar(1));

    const actualizarControles = () => {
        const maxScroll = Math.max(0, track.scrollWidth - track.clientWidth);
        anterior.disabled = track.scrollLeft <= 2;
        siguiente.disabled = track.scrollLeft >= maxScroll - 2;
    };

    track.addEventListener("scroll", actualizarControles, { passive: true });
    window.addEventListener("resize", actualizarControles, { passive: true });

    track.addEventListener("wheel", (evento) => {
        const maxScroll = track.scrollWidth - track.clientWidth;
        if (maxScroll <= 2 || Math.abs(evento.deltaY) <= Math.abs(evento.deltaX)) {
            return;
        }
        const vaDerecha = evento.deltaY > 0;
        const puedeMover = vaDerecha ? track.scrollLeft < maxScroll - 2 : track.scrollLeft > 2;
        if (!puedeMover) {
            return;
        }
        evento.preventDefault();
        track.scrollLeft += evento.deltaY;
    }, { passive: false });

    track.addEventListener("keydown", (evento) => {
        if (evento.key === "ArrowLeft") {
            evento.preventDefault();
            desplazar(-1);
        } else if (evento.key === "ArrowRight") {
            evento.preventDefault();
            desplazar(1);
        }
    });

    actualizarControles();
})();
