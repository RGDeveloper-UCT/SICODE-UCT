(() => {
    const control = document.getElementById("control-anexos-monitoreo");
    if (!control) return;

    const spInput = document.getElementById("no_sp");
    const anexoInput =
        document.getElementById("numero_anexo_monitoreo") ||
        document.getElementById("numero_anexo");
    const vencidoInput = document.getElementById("anexo_vencido");
    const confirmacion = document.getElementById("confirmacion_file_server");
    const submit = document.getElementById("submit");

    const mensajeInicial = document.getElementById("anexos-mensaje-inicial");
    const resumen = document.getElementById("anexos-resumen");
    const spTexto = document.getElementById("anexos-sp");
    const totalTexto = document.getElementById("anexos-total");
    const siguienteTexto = document.getElementById("anexos-siguiente");
    const modoTexto = document.getElementById("anexos-modo");
    const conocidos = document.getElementById("anexos-conocidos");
    const advertencia = document.getElementById("anexos-advertencia");
    const opcionVencido = document.getElementById("opcion-anexo-vencido");
    const mensajeVencido = document.getElementById("modo-vencido-mensaje");
    const notaModo = document.getElementById("anexos-nota-modo");

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
        if (anexoInput) anexoInput.readOnly = true;
        if (vencidoInput) vencidoInput.disabled = bloquear;
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
            "Confirme el total real en File Server.";
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
            if (item.vencido) chip.classList.add("chip-anexo-vencido");
            const numero = item.numero ? `Anexo ${item.numero}` : "Anexo";
            const titulo = item.titulo ? `: ${item.titulo}` : "";
            chip.textContent = `${numero}${titulo}${item.vencido ? " · VENCIDO" : ""}`;
            conocidos.appendChild(chip);
        });
    }

    function numeroActualInput() {
        const valor = Number.parseInt((anexoInput?.value || "").trim(), 10);
        return Number.isInteger(valor) ? valor : null;
    }

    function aplicarModo({ conservarNumeroVencido = true } = {}) {
        if (!estadoActual || estadoActual.requiere_rectificacion || !anexoInput) return;

        const esVencido = Boolean(vencidoInput?.checked);
        opcionVencido?.classList.toggle("activo", esVencido);
        if (mensajeVencido) mensajeVencido.hidden = !esVencido;

        if (esVencido) {
            anexoInput.readOnly = false;
            modoTexto.textContent = "VENCIDO / HISTÓRICO";
            if (notaModo) {
                notaModo.textContent =
                    `Escriba el número físico original entre 1 y ${estadoActual.total_rectificado}. ` +
                    `Al guardar, la secuencia vigente seguirá en ${estadoActual.total_rectificado}.`;
            }
            mostrarAdvertencia(
                `Modo ANEXO VENCIDO activo. Puede registrar un número anterior entre 1 y ${estadoActual.total_rectificado}; ` +
                "este registro NO incrementará el total vigente."
            );

            const actual = numeroActualInput();
            const valido = actual !== null && actual >= 1 && actual <= Number(estadoActual.total_rectificado);
            if (!conservarNumeroVencido || !valido) anexoInput.value = "";
            return;
        }

        anexoInput.readOnly = true;
        anexoInput.value = String(estadoActual.siguiente_anexo);
        modoTexto.textContent = "Vigente";
        if (notaModo) {
            notaModo.textContent =
                `En modo vigente SICODE asigna automáticamente el Anexo ${estadoActual.siguiente_anexo} ` +
                "y actualiza la secuencia al guardar.";
        }
        mostrarAdvertencia(
            `Este registro corresponde al Anexo ${estadoActual.siguiente_anexo}. ` +
            "Si está capturando un anexo anterior que faltaba registrar, active la opción roja «ANEXO VENCIDO / HISTÓRICO»."
        );
    }

    function pintarEstado(data, abrirSiHaceFalta = true) {
        estadoActual = data;
        mensajeInicial.hidden = true;
        resumen.hidden = false;
        spTexto.textContent = data.no_sp;
        totalTexto.textContent =
            data.total_rectificado === null
                ? "Sin rectificar"
                : `Anexo ${data.total_rectificado}`;

        pintarAnexos(data.anexos);
        limpiarConfirmacion();

        if (data.requiere_rectificacion) {
            siguienteTexto.textContent = "Pendiente de confirmar";
            if (modoTexto) modoTexto.textContent = "Bloqueado";
            bloquearRegistro(true);
            if (anexoInput) anexoInput.value = "";
            const razon = data.inconsistente
                ? `El total rectificado (${data.total_rectificado}) es menor que la evidencia ya registrada (${data.minimo_conocido}).`
                : "SICODE todavía no tiene un total de anexos rectificado para este SP.";
            mostrarAdvertencia(
                `${razon} Verifique File Server y rectifique el total antes de registrar anexos vigentes o vencidos.`
            );
            if (abrirSiHaceFalta) abrirModal(true);
            return;
        }

        bloquearRegistro(false);
        siguienteTexto.textContent = `Anexo ${data.siguiente_anexo}`;
        aplicarModo({ conservarNumeroVencido: true });
    }

    async function cargarEstado(abrirSiHaceFalta = true) {
        const sp = (spInput?.value || "").trim();
        if (!sp) {
            ultimoSpConsultado = "";
            estadoActual = null;
            mensajeInicial.hidden = false;
            mensajeInicial.textContent = "Seleccione un SP para consultar la secuencia de anexos.";
            resumen.hidden = true;
            bloquearRegistro(true);
            limpiarConfirmacion();
            if (anexoInput) anexoInput.value = "";
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
            cerrarModal();
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

    vencidoInput?.addEventListener("change", () => {
        limpiarConfirmacion();
        aplicarModo({ conservarNumeroVencido: false });
        if (vencidoInput.checked) window.setTimeout(() => anexoInput?.focus(), 0);
    });

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

        const esVencido = Boolean(vencidoInput?.checked);
        const numero = numeroActualInput();
        if (esVencido) {
            const total = Number(estadoActual.total_rectificado);
            if (numero === null || numero < 1 || numero > total) {
                evento.preventDefault();
                anexoInput?.focus();
                mostrarAdvertencia(
                    `Un anexo vencido debe conservar un número entre 1 y ${total}. La secuencia vigente no se modificará.`
                );
                return;
            }
        } else if (numero !== Number(estadoActual.siguiente_anexo)) {
            evento.preventDefault();
            anexoInput.value = String(estadoActual.siguiente_anexo);
            mostrarAdvertencia(`El anexo vigente debe continuar con el número ${estadoActual.siguiente_anexo}.`);
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
