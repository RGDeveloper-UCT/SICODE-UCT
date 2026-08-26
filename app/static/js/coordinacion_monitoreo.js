(() => {
    const control = document.getElementById("control-anexos-monitoreo");
    if (!control) return;

    const spInput = document.getElementById("no_sp");
    const anexoInput = document.getElementById("numero_anexo_monitoreo");
    const confirmacion = document.getElementById("confirmacion_file_server");
    const submit = document.getElementById("submit");

    const mensajeInicial = document.getElementById("anexos-mensaje-inicial");
    const resumen = document.getElementById("anexos-resumen");
    const spTexto = document.getElementById("anexos-sp");
    const totalTexto = document.getElementById("anexos-total");
    const siguienteTexto = document.getElementById("anexos-siguiente");
    const conocidos = document.getElementById("anexos-conocidos");
    const advertencia = document.getElementById("anexos-advertencia");

    const modal = document.getElementById("modal-rectificacion-anexos");
    const modalContexto = document.getElementById("modal-anexos-contexto");
    const modalError = document.getElementById("modal-anexos-error");
    const totalInput = document.getElementById("rectificar-total-anexos");
    const abrirRectificacion = document.getElementById("abrir-rectificacion-anexos");
    const cerrarRectificacion = document.getElementById("cerrar-rectificacion-anexos");
    const guardarRectificacion = document.getElementById("guardar-rectificacion-anexos");

    const estadoUrl = control.dataset.estadoUrl;
    const rectificarUrl = control.dataset.rectificarUrl;
    const csrf = control.dataset.csrf;

    let estadoActual = null;
    let temporizador = null;
    let ultimoSpConsultado = "";

    function limpiarConfirmacion() {
        if (confirmacion) confirmacion.checked = false;
    }

    function bloquearRegistro(bloquear) {
        if (anexoInput) {
            anexoInput.disabled = bloquear;
            if (bloquear) anexoInput.value = "";
        }
        if (confirmacion) confirmacion.disabled = bloquear;
        if (submit) submit.disabled = bloquear;
    }

    function mostrarAdvertencia(texto) {
        if (!advertencia) return;
        if (!texto) {
            advertencia.hidden = true;
            advertencia.textContent = "";
            return;
        }
        advertencia.textContent = texto;
        advertencia.hidden = false;
    }

    function abrirModal(forzado = false) {
        if (!modal || !estadoActual) return;
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
        modal.dataset.forzado = forzado ? "1" : "0";
        modalError.hidden = true;
        modalError.textContent = "";

        const sugerido = Math.max(
            Number(estadoActual.total_rectificado ?? 0),
            Number(estadoActual.minimo_conocido ?? 0)
        );
        totalInput.value = String(sugerido);
        modalContexto.textContent =
            `SP ${estadoActual.no_sp}. SICODE registra actualmente ` +
            `${estadoActual.total_rectificado === null ? "un total sin rectificar" : estadoActual.total_rectificado + " anexo(s)"}. ` +
            `Confirme el total real en File Server.`;
        window.setTimeout(() => totalInput.focus(), 0);
    }

    function cerrarModal() {
        if (!modal) return;
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
    }

    function pintarAnexos(detalles) {
        if (!conocidos) return;
        conocidos.innerHTML = "";
        if (!detalles || detalles.length === 0) {
            conocidos.textContent = "No hay anexos individualizados. Se utilizará el total rectificado del expediente.";
            return;
        }

        detalles.forEach((item) => {
            const chip = document.createElement("span");
            chip.className = "chip-anexo";
            const numero = item.numero ? `Anexo ${item.numero}` : "Anexo";
            chip.textContent = item.titulo ? `${numero}: ${item.titulo}` : numero;
            conocidos.appendChild(chip);
        });
    }

    function pintarEstado(data, abrirSiHaceFalta = true) {
        estadoActual = data;
        mensajeInicial.hidden = true;
        resumen.hidden = false;
        spTexto.textContent = data.no_sp;
        totalTexto.textContent =
            data.total_rectificado === null
                ? "Sin rectificar"
                : `${data.total_rectificado} anexo(s)`;

        pintarAnexos(data.anexos);
        limpiarConfirmacion();

        if (data.requiere_rectificacion) {
            siguienteTexto.textContent = "Pendiente de confirmar";
            bloquearRegistro(true);
            const razon = data.inconsistente
                ? `El total rectificado (${data.total_rectificado}) es menor que la evidencia ya registrada (${data.minimo_conocido}).`
                : "SICODE todavía no tiene un total de anexos rectificado para este SP.";
            mostrarAdvertencia(
                `${razon} Verifique File Server y rectifique el total antes de registrar el reporte.`
            );
            if (abrirSiHaceFalta) abrirModal(true);
            return;
        }

        bloquearRegistro(false);
        anexoInput.value = String(data.siguiente_anexo);
        siguienteTexto.textContent = `Anexo ${data.siguiente_anexo}`;

        if (data.total_rectificado === 0) {
            mostrarAdvertencia(
                "SICODE registra 0 anexos. Confirme en File Server que este reporte efectivamente corresponde al Anexo 1. " +
                "Si encuentra anexos previos, use «Rectificar anexos»."
            );
        } else {
            mostrarAdvertencia(
                `Según la última rectificación, este reporte corresponde al Anexo ${data.siguiente_anexo}. ` +
                "Confirme el número en File Server antes de guardar."
            );
        }
    }

    async function cargarEstado(abrirSiHaceFalta = true) {
        const sp = (spInput?.value || "").trim();
        if (!sp) {
            ultimoSpConsultado = "";
            estadoActual = null;
            mensajeInicial.hidden = false;
            resumen.hidden = true;
            bloquearRegistro(true);
            limpiarConfirmacion();
            return;
        }

        ultimoSpConsultado = sp;
        mensajeInicial.hidden = false;
        mensajeInicial.textContent = "Consultando anexos del SP…";
        resumen.hidden = true;
        bloquearRegistro(true);

        try {
            const respuesta = await fetch(`${estadoUrl}?no_sp=${encodeURIComponent(sp)}`, {
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
            });
            const data = await respuesta.json();
            if (sp !== (spInput?.value || "").trim()) return;

            if (!respuesta.ok || !data.ok) {
                estadoActual = null;
                mensajeInicial.hidden = false;
                mensajeInicial.textContent = data.mensaje || "No fue posible consultar el SP.";
                resumen.hidden = true;
                bloquearRegistro(true);
                return;
            }

            pintarEstado(data, abrirSiHaceFalta);
        } catch (_error) {
            estadoActual = null;
            mensajeInicial.hidden = false;
            mensajeInicial.textContent = "No fue posible consultar los anexos. Revise la conexión con SICODE.";
            resumen.hidden = true;
            bloquearRegistro(true);
        }
    }

    async function guardarRectificacionActual() {
        if (!estadoActual) return;

        const total = Number(totalInput.value);
        if (!Number.isInteger(total) || total < 0 || total > 200) {
            modalError.textContent = "Indique un total entero entre 0 y 200.";
            modalError.hidden = false;
            return;
        }

        guardarRectificacion.disabled = true;
        modalError.hidden = true;
        try {
            const respuesta = await fetch(rectificarUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    expediente_id: estadoActual.expediente_id,
                    total_anexos: total,
                }),
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok) {
                modalError.textContent = data.mensaje || "No fue posible guardar la rectificación.";
                modalError.hidden = false;
                return;
            }

            modal.dataset.forzado = "0";
            modal.hidden = true;
            modal.setAttribute("aria-hidden", "true");
            await cargarEstado(false);
        } catch (_error) {
            modalError.textContent = "No fue posible guardar la rectificación. Intente nuevamente.";
            modalError.hidden = false;
        } finally {
            guardarRectificacion.disabled = false;
        }
    }

    function programarConsulta() {
        window.clearTimeout(temporizador);
        temporizador = window.setTimeout(() => {
            const sp = (spInput?.value || "").trim();
            if (sp && sp !== ultimoSpConsultado) cargarEstado(true);
        }, 300);
    }

    if (spInput) {
        spInput.addEventListener("input", programarConsulta);
        spInput.addEventListener("change", () => cargarEstado(true));
        spInput.addEventListener("blur", () => {
            const sp = (spInput.value || "").trim();
            if (sp && sp !== ultimoSpConsultado) cargarEstado(true);
        });
    }

    abrirRectificacion?.addEventListener("click", () => abrirModal(false));
    cerrarRectificacion?.addEventListener("click", cerrarModal);
    guardarRectificacion?.addEventListener("click", guardarRectificacionActual);

    modal?.addEventListener("click", (evento) => {
        if (evento.target === modal) cerrarModal();
    });

    document.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape" && modal && !modal.hidden) cerrarModal();
    });

    const formulario = control.closest("form");
    formulario?.addEventListener("submit", (evento) => {
        if (!estadoActual || estadoActual.requiere_rectificacion) {
            evento.preventDefault();
            if (estadoActual) abrirModal(true);
            return;
        }
        if (!confirmacion?.checked) {
            evento.preventDefault();
            confirmacion?.focus();
            mostrarAdvertencia("Debe confirmar en File Server el número de anexo antes de guardar.");
        }
    });

    bloquearRegistro(true);
    if ((spInput?.value || "").trim()) cargarEstado(true);
})();
