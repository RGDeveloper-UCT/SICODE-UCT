(() => {
    const ruta = window.location.pathname || "";
    if (!ruta.startsWith("/coordinacion/")) return;

    const formularios = Array.from(document.querySelectorAll("form")).filter((form) => {
        const metodo = (form.getAttribute("method") || "get").toLowerCase();
        return metodo === "post" && form.querySelector('[name="no_sp"]');
    });
    if (formularios.length === 0) return;

    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    const estadoUrl = "/coordinacion/rectificacion-produccion/estado";
    const guardarUrl = "/coordinacion/rectificacion-produccion/guardar";

    const estilo = document.createElement("style");
    estilo.textContent = `
        .rect-prod-modal[hidden] { display: none !important; }
        .rect-prod-modal {
            position: fixed;
            inset: 0;
            z-index: 1600;
            display: grid;
            place-items: center;
            padding: 20px;
            background: rgba(15, 23, 42, .68);
        }
        .rect-prod-dialogo {
            width: min(680px, 100%);
            max-height: calc(100vh - 40px);
            overflow: auto;
            border-radius: 16px;
            background: #fff;
            box-shadow: 0 26px 80px rgba(15, 23, 42, .34);
        }
        .rect-prod-cabecera {
            padding: 22px 24px 16px;
            border-bottom: 1px solid #dbe3ef;
        }
        .rect-prod-etiqueta {
            display: inline-block;
            margin-bottom: 8px;
            padding: 5px 9px;
            border-radius: 999px;
            background: #fff7ed;
            color: #9a3412;
            font-size: .78rem;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .rect-prod-cabecera h2 { margin: 0 0 8px; }
        .rect-prod-cabecera p { margin: 0; line-height: 1.5; }
        .rect-prod-cuerpo { padding: 20px 24px 24px; }
        .rect-prod-aviso {
            margin-bottom: 16px;
            padding: 14px 16px;
            border: 1px solid #bfdbfe;
            border-left: 4px solid #17233c;
            border-radius: 10px;
            background: #eff6ff;
            line-height: 1.5;
        }
        .rect-prod-estado {
            margin-bottom: 16px;
            padding: 12px 14px;
            border-radius: 10px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            line-height: 1.5;
        }
        .rect-prod-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }
        .rect-prod-campo label {
            display: block;
            margin-bottom: 6px;
            font-weight: 700;
        }
        .rect-prod-campo input[type="number"] {
            width: 100%;
            box-sizing: border-box;
            min-height: 44px;
            padding: 9px 11px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
        }
        .rect-prod-nota {
            margin: 12px 0 0;
            color: #475569;
            font-size: .92rem;
            line-height: 1.45;
        }
        .rect-prod-confirmacion {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            margin-top: 18px;
            padding: 13px 14px;
            border-radius: 10px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            line-height: 1.45;
        }
        .rect-prod-confirmacion input { margin-top: 3px; }
        .rect-prod-error {
            margin-top: 14px;
            padding: 11px 13px;
            border-radius: 8px;
            background: #fef2f2;
            border: 1px solid #fecaca;
            color: #991b1b;
        }
        .rect-prod-acciones {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 20px;
        }
        .rect-prod-acciones button { min-width: 120px; }
        .rect-prod-bloqueado { opacity: .7; cursor: wait; }
        @media (max-width: 660px) {
            .rect-prod-grid { grid-template-columns: 1fr; }
            .rect-prod-acciones { flex-direction: column-reverse; }
            .rect-prod-acciones button { width: 100%; }
        }
    `;
    document.head.appendChild(estilo);

    const modal = document.createElement("div");
    modal.className = "rect-prod-modal";
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
        <div class="rect-prod-dialogo" role="dialog" aria-modal="true" aria-labelledby="rect-prod-titulo">
            <div class="rect-prod-cabecera">
                <span class="rect-prod-etiqueta">Control obligatorio de producción</span>
                <h2 id="rect-prod-titulo">Rectificar expediente antes de guardar</h2>
                <p>
                    SICODE-UCT ya se encuentra en producción. Para alimentar y depurar el registro maestro,
                    cada registro asociado a un SP debe confirmar el total físico actual de folios y anexos.
                </p>
            </div>
            <div class="rect-prod-cuerpo">
                <div class="rect-prod-aviso">
                    <strong>¿Por qué se solicita?</strong> Durante la puesta en producción necesitamos completar
                    progresivamente los datos maestros de cada expediente. Esta confirmación actualiza únicamente
                    metadatos de control; no carga documentos ni copias del expediente.
                </div>
                <div id="rect-prod-estado" class="rect-prod-estado">Consultando expediente…</div>
                <div class="rect-prod-grid">
                    <div class="rect-prod-campo">
                        <label for="rect-prod-folios">Total actual de folios del expediente</label>
                        <input id="rect-prod-folios" type="number" min="1" step="1" inputmode="numeric" autocomplete="off">
                    </div>
                    <div class="rect-prod-campo">
                        <label for="rect-prod-anexos">Total actual de anexos del expediente</label>
                        <input id="rect-prod-anexos" type="number" min="0" max="200" step="1" inputmode="numeric" autocomplete="off">
                    </div>
                </div>
                <p id="rect-prod-nota" class="rect-prod-nota">
                    Escriba 0 en anexos si confirmó que el expediente no contiene ninguno.
                    El total debe representar el estado físico real al momento de guardar este registro.
                </p>
                <label class="rect-prod-confirmacion">
                    <input id="rect-prod-confirmar" type="checkbox">
                    <span>Confirmo que revisé el expediente o el control físico disponible y que los totales indicados son correctos.</span>
                </label>
                <div id="rect-prod-error" class="rect-prod-error" hidden></div>
                <div class="rect-prod-acciones">
                    <button id="rect-prod-cancelar" type="button" class="boton-cancelar">Cancelar</button>
                    <button id="rect-prod-guardar" type="button" class="boton">Rectificar y continuar</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const estado = modal.querySelector("#rect-prod-estado");
    const folios = modal.querySelector("#rect-prod-folios");
    const anexos = modal.querySelector("#rect-prod-anexos");
    const confirmar = modal.querySelector("#rect-prod-confirmar");
    const error = modal.querySelector("#rect-prod-error");
    const cancelar = modal.querySelector("#rect-prod-cancelar");
    const guardar = modal.querySelector("#rect-prod-guardar");
    const nota = modal.querySelector("#rect-prod-nota");

    let formularioActual = null;
    let spActual = "";
    let submitterActual = null;
    let cargando = false;

    function tipoActual() {
        const coincidencia = ruta.match(/^\/coordinacion\/registrar\/([^/]+)/);
        if (coincidencia) return decodeURIComponent(coincidencia[1]).replaceAll("-", " ");
        if (/^\/coordinacion\/remisiones\/\d+\/?$/.test(ruta)) return "agregar expediente a remisión";
        return "registro de Coordinación";
    }

    function mostrarError(mensaje) {
        error.textContent = mensaje || "No fue posible completar la rectificación.";
        error.hidden = false;
    }

    function limpiarError() {
        error.textContent = "";
        error.hidden = true;
    }

    function bloquear(bloqueado) {
        cargando = bloqueado;
        folios.disabled = bloqueado;
        anexos.disabled = bloqueado;
        confirmar.disabled = bloqueado;
        guardar.disabled = bloqueado;
        modal.querySelector(".rect-prod-dialogo")?.classList.toggle("rect-prod-bloqueado", bloqueado);
    }

    function cerrar() {
        if (cargando) return;
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
        formularioActual = null;
        spActual = "";
        submitterActual = null;
    }

    function textoFecha(valor) {
        if (!valor) return "sin rectificación previa";
        const fecha = new Date(valor);
        if (Number.isNaN(fecha.getTime())) return "rectificación previa registrada";
        return fecha.toLocaleString("es-GT", { dateStyle: "short", timeStyle: "short" });
    }

    async function abrir(formulario, sp, submitter) {
        formularioActual = formulario;
        spActual = sp;
        submitterActual = submitter || null;
        limpiarError();
        confirmar.checked = false;
        folios.value = "";
        anexos.value = "";
        anexos.readOnly = false;
        nota.textContent =
            "Escriba 0 en anexos si confirmó que el expediente no contiene ninguno. " +
            "El total debe representar el estado físico real al momento de guardar este registro.";
        estado.innerHTML = `<strong>SP ${sp}</strong> · Consultando rectificación vigente…`;
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        bloquear(true);

        try {
            const respuesta = await fetch(`${estadoUrl}?no_sp=${encodeURIComponent(sp)}`, {
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok) {
                mostrarError(data.mensaje || "No fue posible localizar el SP.");
                estado.innerHTML = `<strong>SP ${sp}</strong> · No disponible para rectificación.`;
                return;
            }

            spActual = String(data.no_sp || sp);
            folios.value = data.folios_rectificados ?? "";
            anexos.value = data.anexos_rectificados ?? "";
            estado.innerHTML =
                `<strong>SP ${data.no_sp}</strong> · Folios actuales en SICODE: ` +
                `<strong>${data.folios_rectificados ?? "sin dato"}</strong> · Anexos: ` +
                `<strong>${data.anexos_rectificados ?? "sin dato"}</strong><br>` +
                `Última confirmación: ${textoFecha(data.rectificado_en)}` +
                `${data.rectificado_por ? ` · por ${data.rectificado_por}` : ""}.`;

            if (ruta.includes("/registrar/monitoreo")) {
                anexos.readOnly = true;
                nota.textContent =
                    "En Reporte de monitoreo, el total de anexos se controla primero con «Rectificar anexos» y la confirmación de File Server. " +
                    "Aquí se vuelve a confirmar ese total junto con los folios antes de guardar el registro.";
            } else if (ruta.includes("/registrar/anexo")) {
                nota.textContent =
                    "Para un registro de anexo, confirme el estado físico actual del expediente. " +
                    "Si el anexo que está registrando ya fue incorporado físicamente, el total de anexos debe incluirlo.";
            }
        } catch (_error) {
            estado.innerHTML = `<strong>SP ${sp}</strong> · No fue posible consultar el expediente.`;
            mostrarError("No fue posible consultar SICODE. Revise la conexión e intente nuevamente.");
        } finally {
            bloquear(false);
            if (!anexos.readOnly) anexos.disabled = false;
            folios.focus();
        }
    }

    async function guardarRectificacion() {
        if (!formularioActual || !spActual || cargando) return;
        limpiarError();

        const totalFolios = Number(folios.value);
        const totalAnexos = Number(anexos.value);
        if (!Number.isInteger(totalFolios) || totalFolios < 1) {
            mostrarError("Indique el total actual de folios con un número entero mayor que cero.");
            folios.focus();
            return;
        }
        if (!Number.isInteger(totalAnexos) || totalAnexos < 0 || totalAnexos > 200) {
            mostrarError("Indique el total actual de anexos con un número entero entre 0 y 200.");
            anexos.focus();
            return;
        }
        if (!confirmar.checked) {
            mostrarError("Debe confirmar que verificó los totales antes de continuar.");
            confirmar.focus();
            return;
        }

        bloquear(true);
        try {
            const respuesta = await fetch(guardarUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    no_sp: spActual,
                    total_folios: totalFolios,
                    total_anexos: totalAnexos,
                    confirmado: true,
                    origen: tipoActual(),
                }),
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok) {
                mostrarError(data.mensaje || "No fue posible guardar la rectificación.");
                return;
            }

            const formulario = formularioActual;
            const submitter = submitterActual;
            formulario.dataset.rectificacionProduccionConfirmada = String(data.no_sp || spActual);
            modal.hidden = true;
            modal.setAttribute("aria-hidden", "true");
            formularioActual = null;
            spActual = "";
            submitterActual = null;
            bloquear(false);

            if (typeof formulario.requestSubmit === "function") {
                if (submitter && formulario.contains(submitter)) formulario.requestSubmit(submitter);
                else formulario.requestSubmit();
            } else {
                formulario.submit();
            }
        } catch (_error) {
            mostrarError("No fue posible guardar la rectificación. Intente nuevamente.");
        } finally {
            if (!modal.hidden) bloquear(false);
        }
    }

    formularios.forEach((formulario) => {
        const spInput = formulario.querySelector('[name="no_sp"]');
        if (!spInput) return;

        const limpiarConfirmacion = () => {
            const actual = (spInput.value || "").trim();
            if (formulario.dataset.rectificacionProduccionConfirmada !== actual) {
                delete formulario.dataset.rectificacionProduccionConfirmada;
            }
        };
        spInput.addEventListener("input", limpiarConfirmacion);
        spInput.addEventListener("change", limpiarConfirmacion);

        formulario.addEventListener("submit", (evento) => {
            if (evento.defaultPrevented) return;
            const sp = (spInput.value || "").trim();
            if (!sp) return;
            if (formulario.dataset.rectificacionProduccionConfirmada === sp) return;

            evento.preventDefault();
            abrir(formulario, sp, evento.submitter);
        });
    });

    cancelar.addEventListener("click", cerrar);
    guardar.addEventListener("click", guardarRectificacion);
    modal.addEventListener("click", (evento) => {
        if (evento.target === modal) cerrar();
    });
    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape" && !modal.hidden) cerrar();
    });
})();
