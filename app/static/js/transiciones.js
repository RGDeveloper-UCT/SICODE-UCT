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
