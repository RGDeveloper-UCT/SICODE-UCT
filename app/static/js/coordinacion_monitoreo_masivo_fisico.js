(() => {
    const root = document.getElementById("monitoreo-masivo");
    const modal = document.getElementById("modal-rectificacion-masiva");
    if (!root || !modal) return;

    const rectificarUrl = root.dataset.rectificarUrl || "";
    const estadoMasivoUrl = root.dataset.estadoUrl || "";
    const estadoFisicoUrl = "/coordinacion/rectificacion-produccion/estado";
    const folios = document.getElementById("masivo-total-folios");
    const anexos = document.getElementById("masivo-total-anexos");
    const confirmar = document.getElementById("masivo-confirmar-rectificacion");
    const guardar = document.getElementById("guardar-rectificacion");
    const textoModal = document.getElementById("texto-rectificacion-masiva");
    const tabla = document.getElementById("filas-monitoreo");
    if (!folios || !anexos || !confirmar || !guardar || !tabla) return;

    const confirmacionTexto = confirmar.parentElement?.querySelector("span");
    const textoModalOriginal = textoModal?.textContent || "";
    const confirmacionOriginal = confirmacionTexto?.textContent || "";
    const botonOriginal = guardar.textContent;
    let spActual = "";
    let valorFoliosPrevio = "";
    const sinFisicoSp = new Map();

    const estilo = document.createElement("style");
    estilo.textContent = `
        .masivo-sin-fisico {
            display:flex;
            align-items:flex-start;
            gap:10px;
            margin:14px 0;
            padding:12px 13px;
            border:1px solid #fecaca;
            border-radius:9px;
            background:#fef2f2;
            color:#7f1d1d;
            cursor:pointer;
            line-height:1.4;
        }
        .masivo-sin-fisico input { width:auto!important; min-height:auto!important; margin-top:3px; }
        .masivo-sin-fisico strong { display:block; margin-bottom:2px; }
        .masivo-sin-fisico small { display:block; color:#991b1b; }
        .estado-rect-badge.sin-fisico { background:#fef2f2!important; color:#b91c1c!important; }
        #masivo-total-folios:disabled { background:#f1f5f9; color:#64748b; cursor:not-allowed; }
    `;
    document.head.appendChild(estilo);

    const etiqueta = document.createElement("label");
    etiqueta.className = "masivo-sin-fisico";
    etiqueta.innerHTML = `
        <input id="masivo-sin-expediente-fisico" type="checkbox">
        <span>
            <strong>No se cuenta con el expediente físico aún</strong>
            <small>Marque esta opción cuando el SP existe, pero el expediente principal todavía no ha sido recibido en Coordinación. No se registrarán folios ficticios.</small>
        </span>
    `;
    const grid = modal.querySelector(".modal-masivo-grid");
    if (grid) grid.parentNode.insertBefore(etiqueta, grid);
    const sinFisico = etiqueta.querySelector("input");

    function filasDelSp(sp) {
        return Array.from(tabla.querySelectorAll("tr")).filter(
            (tr) => tr.querySelector(".fila-sp")?.value.trim() === sp
        );
    }

    function actualizarBadges() {
        Array.from(tabla.querySelectorAll("tr")).forEach((tr) => {
            const sp = tr.querySelector(".fila-sp")?.value.trim();
            const badge = tr.querySelector(".estado-rect-badge");
            const boton = tr.querySelector(".fila-rectificar");
            if (!sp || !badge) return;
            if (sinFisicoSp.has(sp)) {
                const totalAnexos = sinFisicoSp.get(sp);
                const deseado = `Sin expediente físico · ${totalAnexos} anexos`;
                if (badge.textContent !== deseado) badge.textContent = deseado;
                badge.classList.remove("ok");
                badge.classList.add("sin-fisico");
                if (boton) boton.textContent = "Confirmar de nuevo";
            } else {
                badge.classList.remove("sin-fisico");
            }
        });
    }

    function aplicarModoSinFisico(activo) {
        sinFisico.checked = Boolean(activo);
        if (sinFisico.checked) {
            if (!folios.disabled) valorFoliosPrevio = folios.value;
            folios.value = "";
            folios.disabled = true;
            if (textoModal) {
                textoModal.textContent =
                    "Confirme que el expediente físico todavía no ha sido recibido. El total de anexos sigue siendo necesario para calcular el correlativo de los reportes del lote.";
            }
            if (confirmacionTexto) {
                confirmacionTexto.textContent =
                    "Confirmo que el expediente físico principal todavía no ha sido recibido en Coordinación y que el total de anexos indicado corresponde al control disponible/File Server.";
            }
            guardar.textContent = "Confirmar estado y continuar";
        } else {
            folios.disabled = false;
            folios.value = valorFoliosPrevio || folios.value || "";
            if (textoModal) textoModal.textContent = textoModalOriginal;
            if (confirmacionTexto) confirmacionTexto.textContent = confirmacionOriginal;
            guardar.textContent = botonOriginal;
        }
    }

    async function cargarEstadoFisico(sp) {
        if (!sp) return;
        try {
            const respuesta = await fetch(`${estadoFisicoUrl}?no_sp=${encodeURIComponent(sp)}`, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok || sp !== spActual) return;
            valorFoliosPrevio = data.folios_rectificados ?? "";
            aplicarModoSinFisico(data.expediente_fisico_registrado === false);
        } catch (_error) {
            // El flujo masivo conserva su propia validación; un fallo de esta
            // consulta auxiliar no debe bloquear la rectificación normal.
        }
    }

    root.addEventListener("click", (evento) => {
        const boton = evento.target.closest?.(".fila-rectificar");
        if (!boton) return;
        const tr = boton.closest("tr");
        const sp = tr?.querySelector(".fila-sp")?.value.trim() || "";
        spActual = sp;
        valorFoliosPrevio = "";
    }, true);

    const observadorModal = new MutationObserver(() => {
        if (!modal.hidden && spActual) cargarEstadoFisico(spActual);
    });
    observadorModal.observe(modal, { attributes: true, attributeFilter: ["hidden", "aria-hidden"] });

    sinFisico.addEventListener("change", () => {
        if (!sinFisico.checked) valorFoliosPrevio = valorFoliosPrevio || "";
        aplicarModoSinFisico(sinFisico.checked);
        if (sinFisico.checked) anexos.focus();
        else folios.focus();
    });

    // El JS histórico valida el total de folios antes de hacer fetch. Cuando
    // se confirma ausencia física colocamos un valor temporal sólo durante el
    // evento; el interceptor de fetch lo sustituye por null antes de enviarlo.
    guardar.addEventListener("click", () => {
        if (!sinFisico.checked) return;
        folios.value = "1";
        queueMicrotask(() => {
            if (sinFisico.checked) {
                folios.value = "";
                folios.disabled = true;
            }
        });
    }, true);

    const fetchOriginal = window.fetch.bind(window);
    window.fetch = async (entrada, opciones = {}) => {
        const url = typeof entrada === "string" ? entrada : (entrada?.url || "");
        let opcionesFinales = opciones;

        if (rectificarUrl && url.includes(rectificarUrl) && String(opciones.method || "GET").toUpperCase() === "POST") {
            try {
                const cuerpo = JSON.parse(opciones.body || "{}");
                if (cuerpo.no_sp) spActual = String(cuerpo.no_sp);
                cuerpo.sin_expediente_fisico = Boolean(sinFisico.checked && cuerpo.no_sp === spActual);
                if (cuerpo.sin_expediente_fisico) cuerpo.total_folios = null;
                opcionesFinales = { ...opciones, body: JSON.stringify(cuerpo) };
            } catch (_error) {
                opcionesFinales = opciones;
            }
        }

        const respuesta = await fetchOriginal(entrada, opcionesFinales);

        if (rectificarUrl && url.includes(rectificarUrl)) {
            respuesta.clone().json().then((data) => {
                const sp = String(data.no_sp || spActual || "");
                if (!sp || !data.ok) return;
                if (data.expediente_fisico_registrado === false || data.folios_rectificados == null) {
                    sinFisicoSp.set(sp, Number(data.anexos_rectificados || 0));
                } else {
                    sinFisicoSp.delete(sp);
                }
                window.requestAnimationFrame(actualizarBadges);
            }).catch(() => {});
        } else if (estadoMasivoUrl && url.includes(estadoMasivoUrl)) {
            respuesta.clone().json().then((data) => {
                let sp = "";
                try {
                    sp = new URL(url, window.location.origin).searchParams.get("no_sp") || "";
                } catch (_error) {
                    sp = "";
                }
                if (!sp || !data.ok) return;
                if (data.rectificado_lote && data.folios_rectificados == null) {
                    sinFisicoSp.set(sp, Number(data.anexos_rectificados || 0));
                } else if (data.rectificado_lote && data.folios_rectificados != null) {
                    sinFisicoSp.delete(sp);
                }
                window.requestAnimationFrame(actualizarBadges);
            }).catch(() => {});
        }

        return respuesta;
    };

    const observadorTabla = new MutationObserver(actualizarBadges);
    observadorTabla.observe(tabla, { childList: true, subtree: true, characterData: true });
})();
