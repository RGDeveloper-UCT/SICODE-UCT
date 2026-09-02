(() => {
    const root = document.getElementById("monitoreo-masivo");
    if (!root) return;

    const loteId = root.dataset.loteId;
    const estadoUrl = root.dataset.estadoUrl;
    const rectificarUrl = root.dataset.rectificarUrl;
    const guardarUrl = root.dataset.guardarUrl;
    const maxReportes = Number(root.dataset.maxReportes || 30);
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";

    const tbody = document.getElementById("filas-monitoreo");
    const errorGeneral = document.getElementById("masivo-error");
    const botonAgregar = document.getElementById("agregar-fila");
    const botonAgregarDiez = document.getElementById("agregar-diez");
    const botonRevisar = document.getElementById("revisar-lote");

    const modalRect = document.getElementById("modal-rectificacion-masiva");
    const tituloRect = document.getElementById("titulo-rectificacion-masiva");
    const textoRect = document.getElementById("texto-rectificacion-masiva");
    const foliosRect = document.getElementById("masivo-total-folios");
    const anexosRect = document.getElementById("masivo-total-anexos");
    const checkRect = document.getElementById("masivo-confirmar-rectificacion");
    const errorRect = document.getElementById("rectificacion-error");
    const guardarRect = document.getElementById("guardar-rectificacion");
    const cancelarRect = document.getElementById("cancelar-rectificacion");

    const modalRevision = document.getElementById("modal-revision-lote");
    const revisionRc = document.getElementById("revision-rc");
    const revisionProvidencia = document.getElementById("revision-providencia");
    const revisionFecha = document.getElementById("revision-fecha");
    const revisionTotal = document.getElementById("revision-total");
    const revisionFilas = document.getElementById("revision-filas");
    const checkFinal = document.getElementById("confirmacion-final-lote");
    const botonConfirmar = document.getElementById("confirmar-registro-lote");
    const volverEdicion = document.getElementById("volver-edicion");
    const errorRevision = document.getElementById("revision-error");
    const exito = document.getElementById("masivo-exito");
    const exitoTexto = document.getElementById("masivo-exito-texto");

    const estadosSp = new Map();
    const temporizadores = new WeakMap();
    let filaRectificando = null;

    function instalarVistaCompacta() {
        if (document.getElementById("monitoreo-masivo-viewport-css")) return;
        const estilo = document.createElement("style");
        estilo.id = "monitoreo-masivo-viewport-css";
        estilo.textContent = `
            body.vista-monitoreo-masivo {
                overflow: hidden !important;
            }
            body.vista-monitoreo-masivo .contenedor {
                width: 100% !important;
                max-width: none !important;
                height: calc(100vh - var(--masivo-topbar-h, 50px)) !important;
                margin: 0 !important;
                padding: 10px 16px 8px !important;
                overflow: hidden !important;
            }
            body.vista-monitoreo-masivo .pie-sicode {
                display: none !important;
            }
            body.vista-monitoreo-masivo .masivo-shell {
                width: 100% !important;
                max-width: none !important;
                height: 100% !important;
                margin: 0 !important;
                display: grid !important;
                grid-template-rows: auto auto minmax(0, 1fr) !important;
                gap: 8px !important;
                overflow: hidden !important;
            }
            body.vista-monitoreo-masivo .masivo-hero {
                margin: 0 !important;
                padding: 8px 14px !important;
                gap: 12px !important;
                border-radius: 10px !important;
                min-height: 58px;
            }
            body.vista-monitoreo-masivo .masivo-hero-identidad {
                gap: 10px !important;
                min-width: 0;
            }
            body.vista-monitoreo-masivo .masivo-radar {
                width: 44px !important;
                height: 44px !important;
                border-radius: 12px !important;
                flex: 0 0 44px;
            }
            body.vista-monitoreo-masivo .masivo-hero h1 {
                margin-bottom: 2px !important;
                font-size: clamp(1.18rem, 1.55vw, 1.55rem) !important;
                line-height: 1.05 !important;
            }
            body.vista-monitoreo-masivo .masivo-hero p {
                font-size: .76rem !important;
                line-height: 1.15 !important;
            }
            body.vista-monitoreo-masivo .masivo-paso {
                margin-top: 4px !important;
                padding: 2px 7px !important;
                font-size: .64rem !important;
            }
            body.vista-monitoreo-masivo .masivo-cabecera,
            body.vista-monitoreo-masivo .masivo-tabla-panel {
                margin: 0 !important;
                border-radius: 10px !important;
            }
            body.vista-monitoreo-masivo .masivo-cabecera {
                padding: 8px 12px !important;
            }
            body.vista-monitoreo-masivo .masivo-cabecera h2,
            body.vista-monitoreo-masivo .masivo-tabla-panel h2 {
                margin: 0 0 5px !important;
                font-size: .88rem !important;
            }
            body.vista-monitoreo-masivo .masivo-grid {
                grid-template-columns: 90px minmax(130px, .9fr) minmax(140px, 1fr) 140px minmax(180px, 1.2fr) !important;
                gap: 7px !important;
            }
            body.vista-monitoreo-masivo .masivo-campo label {
                margin-bottom: 3px !important;
                font-size: .67rem !important;
            }
            body.vista-monitoreo-masivo .masivo-campo input,
            body.vista-monitoreo-masivo .masivo-campo select,
            body.vista-monitoreo-masivo .masivo-tabla input,
            body.vista-monitoreo-masivo .masivo-tabla select {
                min-height: 28px !important;
                height: 28px !important;
                padding: 3px 6px !important;
                border-radius: 6px !important;
                font-size: .72rem !important;
            }
            body.vista-monitoreo-masivo .masivo-recibe {
                margin-top: 5px !important;
                padding: 4px 8px !important;
                min-height: 24px;
                font-size: .69rem !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla-panel {
                min-height: 0 !important;
                padding: 7px 10px 8px !important;
                display: flex !important;
                flex-direction: column !important;
                overflow: hidden !important;
            }
            body.vista-monitoreo-masivo .masivo-toolbar {
                margin-bottom: 5px !important;
                gap: 8px !important;
                flex: 0 0 auto;
            }
            body.vista-monitoreo-masivo .masivo-toolbar > div:first-child {
                min-width: 0;
            }
            body.vista-monitoreo-masivo .masivo-nota {
                margin: 2px 0 0 !important;
                font-size: .66rem !important;
                line-height: 1.15 !important;
            }
            body.vista-monitoreo-masivo .masivo-toolbar-acciones {
                gap: 5px !important;
                flex-wrap: nowrap !important;
            }
            body.vista-monitoreo-masivo .boton-mini {
                min-height: 27px !important;
                padding: 4px 7px !important;
                border-radius: 6px !important;
                font-size: .67rem !important;
                white-space: nowrap;
            }
            body.vista-monitoreo-masivo .masivo-tabla-wrap {
                flex: 1 1 auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow-x: hidden !important;
                overflow-y: auto !important;
                scrollbar-gutter: stable;
                border-radius: 8px !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla {
                width: 100% !important;
                min-width: 0 !important;
                table-layout: fixed !important;
                font-size: .7rem !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla th {
                padding: 5px 5px !important;
                white-space: normal !important;
                line-height: 1.05 !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla td {
                padding: 3px 4px !important;
                transition: background-color .18s ease, border-color .18s ease;
            }
            body.vista-monitoreo-masivo .masivo-col-num { width: 30px !important; }
            body.vista-monitoreo-masivo .masivo-col-sp { width: 8% !important; }
            body.vista-monitoreo-masivo .masivo-col-reporte { width: 10% !important; }
            body.vista-monitoreo-masivo .masivo-col-evento { width: 15% !important; }
            body.vista-monitoreo-masivo .masivo-col-folios { width: 9% !important; }
            body.vista-monitoreo-masivo .masivo-col-modo { width: 12% !important; }
            body.vista-monitoreo-masivo .masivo-col-anexo { width: 7% !important; }
            body.vista-monitoreo-masivo .masivo-col-rect { width: 22% !important; }
            body.vista-monitoreo-masivo .masivo-col-accion { width: 34px !important; }
            body.vista-monitoreo-masivo .estado-rect {
                gap: 4px !important;
                min-width: 0;
            }
            body.vista-monitoreo-masivo .estado-rect-badge {
                min-height: 24px !important;
                padding: 3px 6px !important;
                font-size: .63rem !important;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 58%;
            }
            body.vista-monitoreo-masivo .fila-rectificar {
                flex: 1 1 auto;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            body.vista-monitoreo-masivo .boton-eliminar-fila {
                width: 26px !important;
                height: 26px !important;
                border-radius: 6px !important;
                font-size: .95rem !important;
            }
            body.vista-monitoreo-masivo .masivo-acciones-finales {
                margin-top: 6px !important;
                flex: 0 0 auto;
            }
            body.vista-monitoreo-masivo .masivo-acciones-finales .boton {
                min-height: 30px !important;
                padding: 6px 10px !important;
                font-size: .72rem !important;
            }
            body.vista-monitoreo-masivo .masivo-error {
                margin-top: 5px !important;
                padding: 6px 8px !important;
                font-size: .7rem !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-lista td {
                background: #f0fdf4 !important;
                border-bottom-color: #bbf7d0 !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-lista:nth-child(even) td {
                background: #ecfdf5 !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-lista td:first-child {
                box-shadow: inset 3px 0 0 #86efac;
                color: #166534;
            }
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-lista input,
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-lista select {
                background: rgba(255, 255, 255, .78) !important;
                border-color: #bbf7d0 !important;
            }
            body.vista-monitoreo-masivo .masivo-tabla tr.fila-error td {
                background: #fff7ed !important;
            }
            @media (max-height: 760px) {
                body.vista-monitoreo-masivo .contenedor {
                    padding-top: 6px !important;
                    padding-bottom: 5px !important;
                }
                body.vista-monitoreo-masivo .masivo-shell {
                    gap: 5px !important;
                }
                body.vista-monitoreo-masivo .masivo-hero {
                    min-height: 48px;
                    padding-top: 5px !important;
                    padding-bottom: 5px !important;
                }
                body.vista-monitoreo-masivo .masivo-radar {
                    width: 38px !important;
                    height: 38px !important;
                    flex-basis: 38px;
                }
                body.vista-monitoreo-masivo .masivo-paso {
                    display: none !important;
                }
                body.vista-monitoreo-masivo .masivo-cabecera {
                    padding-top: 6px !important;
                    padding-bottom: 6px !important;
                }
                body.vista-monitoreo-masivo .masivo-recibe {
                    margin-top: 3px !important;
                    padding-top: 2px !important;
                    padding-bottom: 2px !important;
                }
                body.vista-monitoreo-masivo .masivo-campo input,
                body.vista-monitoreo-masivo .masivo-campo select,
                body.vista-monitoreo-masivo .masivo-tabla input,
                body.vista-monitoreo-masivo .masivo-tabla select {
                    min-height: 25px !important;
                    height: 25px !important;
                }
                body.vista-monitoreo-masivo .masivo-tabla th {
                    padding-top: 3px !important;
                    padding-bottom: 3px !important;
                }
                body.vista-monitoreo-masivo .masivo-tabla td {
                    padding-top: 2px !important;
                    padding-bottom: 2px !important;
                }
            }
            @media (max-width: 1150px) {
                body.vista-monitoreo-masivo {
                    overflow: auto !important;
                }
                body.vista-monitoreo-masivo .contenedor {
                    height: auto !important;
                    min-height: calc(100vh - var(--masivo-topbar-h, 50px));
                    overflow: visible !important;
                }
                body.vista-monitoreo-masivo .masivo-shell {
                    height: auto !important;
                    overflow: visible !important;
                }
                body.vista-monitoreo-masivo .masivo-tabla-panel {
                    min-height: 520px !important;
                }
            }
        `;
        document.head.appendChild(estilo);
    }

    function sincronizarAlturaViewport() {
        const topbar = document.querySelector(".topbar");
        const altura = topbar ? Math.ceil(topbar.getBoundingClientRect().height) : 50;
        document.documentElement.style.setProperty("--masivo-topbar-h", `${altura}px`);
    }

    function mostrarError(elemento, texto) {
        elemento.textContent = texto || "";
        elemento.hidden = !texto;
    }

    function abrirModal(modal) {
        modal.hidden = false;
        modal.setAttribute("aria-hidden", "false");
    }

    function cerrarModal(modal) {
        modal.hidden = true;
        modal.setAttribute("aria-hidden", "true");
    }

    function filas() {
        return Array.from(tbody.querySelectorAll("tr"));
    }

    function renumerar() {
        filas().forEach((tr, i) => {
            tr.querySelector(".masivo-col-num").textContent = String(i + 1);
        });
    }

    function filaTieneDatos(tr) {
        return [
            tr.querySelector(".fila-sp")?.value,
            tr.querySelector(".fila-reporte")?.value,
            tr.querySelector(".fila-evento")?.value,
            tr.querySelector(".fila-folios")?.value,
            tr.querySelector(".fila-anexo")?.value,
        ].some((v) => String(v || "").trim());
    }

    function filaEstaLista(tr) {
        const noSp = tr.querySelector(".fila-sp")?.value.trim() || "";
        const numeroReporte = tr.querySelector(".fila-reporte")?.value.trim() || "";
        const tipoEvento = tr.querySelector(".fila-evento")?.value.trim() || "";
        const folios = tr.querySelector(".fila-folios")?.value.trim() || "";
        const modo = tr.querySelector(".fila-modo")?.value || "vigente";
        const numeroAnexo = Number(tr.querySelector(".fila-anexo")?.value);
        const estado = estadoParaSp(noSp);

        if (!noSp || !numeroReporte || !tipoEvento || !folios) return false;
        if (!estado?.rectificado_lote) return false;
        if (!Number.isInteger(numeroAnexo) || numeroAnexo < 1 || numeroAnexo > 200) return false;
        if (modo === "vencido" && numeroAnexo > Number(estado.anexos_rectificados)) return false;
        return true;
    }

    function actualizarEstadoVisual(tr) {
        tr.classList.toggle("fila-lista", filaEstaLista(tr));
    }

    function actualizarFilasPorSp(sp) {
        const clave = String(sp || "").trim();
        filas().forEach((tr) => {
            if (!clave || tr.querySelector(".fila-sp").value.trim() === clave) {
                actualizarEstadoVisual(tr);
            }
        });
    }

    function estadoBadge(tr, estado) {
        const badge = tr.querySelector(".estado-rect-badge");
        const boton = tr.querySelector(".fila-rectificar");
        if (!estado) {
            badge.textContent = "Pendiente";
            badge.classList.remove("ok");
            boton.textContent = "Rectificar";
            actualizarEstadoVisual(tr);
            return;
        }
        if (estado.cargando) {
            badge.textContent = "Consultando…";
            badge.classList.remove("ok");
            boton.textContent = "Rectificar";
            tr.classList.remove("fila-lista");
            return;
        }
        if (estado.error) {
            badge.textContent = "SP no válido";
            badge.classList.remove("ok");
            boton.textContent = "Revisar SP";
            tr.classList.remove("fila-lista");
            return;
        }
        if (estado.rectificado_lote) {
            badge.textContent = `${estado.folios_rectificados} folios · ${estado.anexos_rectificados} anexos`;
            badge.classList.add("ok");
            boton.textContent = "Rectificar de nuevo";
        } else {
            badge.textContent = "Pendiente de rectificar";
            badge.classList.remove("ok");
            boton.textContent = "Rectificar";
        }
        actualizarEstadoVisual(tr);
    }

    function estadoParaSp(sp) {
        return estadosSp.get(String(sp || "").trim()) || null;
    }

    function recalcularAnexos(sp) {
        const clave = String(sp || "").trim();
        if (!clave) return;
        const estado = estadoParaSp(clave);
        if (!estado || !estado.rectificado_lote) {
            actualizarFilasPorSp(clave);
            return;
        }

        let siguiente = Number(estado.anexos_rectificados) + 1;
        filas().forEach((tr) => {
            if (tr.querySelector(".fila-sp").value.trim() !== clave) return;
            const modo = tr.querySelector(".fila-modo").value;
            const anexo = tr.querySelector(".fila-anexo");
            if (modo === "vigente") {
                anexo.readOnly = true;
                anexo.value = String(siguiente);
                siguiente += 1;
            } else {
                anexo.readOnly = false;
                const actual = Number(anexo.value);
                if (!Number.isInteger(actual) || actual < 1 || actual > Number(estado.anexos_rectificados)) {
                    anexo.value = "";
                }
                anexo.placeholder = `1-${estado.anexos_rectificados}`;
            }
            actualizarEstadoVisual(tr);
        });
    }

    async function consultarSp(tr) {
        const input = tr.querySelector(".fila-sp");
        const sp = input.value.trim();
        if (!sp) {
            estadoBadge(tr, null);
            tr.querySelector(".fila-anexo").value = "";
            actualizarEstadoVisual(tr);
            return;
        }

        estadoBadge(tr, { cargando: true });
        try {
            const respuesta = await fetch(
                `${estadoUrl}?lote_id=${encodeURIComponent(loteId)}&no_sp=${encodeURIComponent(sp)}`,
                { credentials: "same-origin", headers: { Accept: "application/json" } }
            );
            const data = await respuesta.json();
            if (sp !== input.value.trim()) return;
            if (!respuesta.ok || !data.ok) {
                estadosSp.set(sp, { error: true, mensaje: data.mensaje || "SP no válido" });
                estadoBadge(tr, estadosSp.get(sp));
                return;
            }
            estadosSp.set(sp, data);
            filas().forEach((otra) => {
                if (otra.querySelector(".fila-sp").value.trim() === sp) estadoBadge(otra, data);
            });
            recalcularAnexos(sp);
        } catch (_error) {
            estadosSp.set(sp, { error: true, mensaje: "No fue posible consultar el SP." });
            estadoBadge(tr, estadosSp.get(sp));
        }
    }

    function programarConsulta(tr) {
        const previo = temporizadores.get(tr);
        if (previo) window.clearTimeout(previo);
        const id = window.setTimeout(() => consultarSp(tr), 280);
        temporizadores.set(tr, id);
    }

    function nuevaFila() {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="masivo-col-num"></td>
            <td class="masivo-col-sp"><input class="fila-sp" list="masivo-sp-list" autocomplete="off" placeholder="SP"></td>
            <td class="masivo-col-reporte"><input class="fila-reporte" maxlength="120" autocomplete="off" placeholder="No. reporte"></td>
            <td class="masivo-col-evento"><input class="fila-evento" list="masivo-eventos-list" maxlength="180" autocomplete="off" placeholder="Tipo de evento"></td>
            <td class="masivo-col-folios"><input class="fila-folios" maxlength="80" autocomplete="off" placeholder="Ej. 325-330"></td>
            <td class="masivo-col-modo">
                <select class="fila-modo">
                    <option value="vigente">Vigente</option>
                    <option value="vencido">Vencido / histórico</option>
                </select>
            </td>
            <td class="masivo-col-anexo"><input class="fila-anexo" type="number" min="1" max="200" step="1" inputmode="numeric" readonly></td>
            <td class="masivo-col-rect">
                <div class="estado-rect">
                    <span class="estado-rect-badge">Pendiente</span>
                    <button class="boton-mini fila-rectificar" type="button">Rectificar</button>
                </div>
            </td>
            <td class="masivo-col-accion"><button class="boton-eliminar-fila" type="button" aria-label="Eliminar fila">×</button></td>
        `;

        const spInput = tr.querySelector(".fila-sp");
        const camposFila = tr.querySelectorAll(".fila-reporte, .fila-evento, .fila-folios, .fila-anexo");

        spInput.addEventListener("input", () => {
            tr.classList.remove("fila-error", "fila-lista");
            programarConsulta(tr);
        });
        spInput.addEventListener("change", () => consultarSp(tr));
        spInput.addEventListener("blur", () => {
            if (spInput.value.trim()) consultarSp(tr);
        });

        camposFila.forEach((campo) => {
            campo.addEventListener("input", () => {
                tr.classList.remove("fila-error");
                actualizarEstadoVisual(tr);
            });
            campo.addEventListener("change", () => actualizarEstadoVisual(tr));
        });

        tr.querySelector(".fila-modo").addEventListener("change", () => {
            tr.classList.remove("fila-error");
            const sp = spInput.value.trim();
            recalcularAnexos(sp);
            actualizarEstadoVisual(tr);
        });

        tr.querySelector(".fila-rectificar").addEventListener("click", async () => {
            const sp = spInput.value.trim();
            if (!sp) {
                tr.classList.add("fila-error");
                mostrarError(errorGeneral, "Indique el SP antes de rectificar el expediente.");
                spInput.focus();
                return;
            }
            await consultarSp(tr);
            const estado = estadoParaSp(sp);
            if (!estado || estado.error) {
                mostrarError(errorGeneral, estado?.mensaje || "No fue posible localizar el SP.");
                return;
            }
            filaRectificando = tr;
            tituloRect.textContent = `Rectificar expediente · SP ${sp}`;
            textoRect.textContent =
                "Confirme los totales reales actuales antes de incorporar cualquier reporte de este lote.";
            foliosRect.value = estado.folios_rectificados ?? "";
            anexosRect.value = estado.anexos_rectificados ?? Math.max(0, Number(estado.minimo_anexos_conocido || 0));
            anexosRect.min = String(Number(estado.minimo_anexos_conocido || 0));
            checkRect.checked = false;
            mostrarError(errorRect, "");
            abrirModal(modalRect);
            window.setTimeout(() => foliosRect.focus(), 0);
        });

        tr.querySelector(".boton-eliminar-fila").addEventListener("click", () => {
            const sp = spInput.value.trim();
            tr.remove();
            renumerar();
            if (sp) recalcularAnexos(sp);
            if (filas().length === 0) agregarFilas(1);
        });

        tbody.appendChild(tr);
        renumerar();
        actualizarEstadoVisual(tr);
        return tr;
    }

    function agregarFilas(cantidad) {
        const disponibles = maxReportes - filas().length;
        const total = Math.min(cantidad, Math.max(0, disponibles));
        for (let i = 0; i < total; i += 1) nuevaFila();
        if (total < cantidad) mostrarError(errorGeneral, `El máximo por lote es de ${maxReportes} reportes.`);
    }

    async function guardarRectificacion() {
        if (!filaRectificando) return;
        const sp = filaRectificando.querySelector(".fila-sp").value.trim();
        const totalFolios = Number(foliosRect.value);
        const totalAnexos = Number(anexosRect.value);

        if (!Number.isInteger(totalFolios) || totalFolios < 1) {
            mostrarError(errorRect, "Indique un total de folios mayor que cero.");
            return;
        }
        if (!Number.isInteger(totalAnexos) || totalAnexos < Number(anexosRect.min || 0) || totalAnexos > 200) {
            mostrarError(errorRect, `Indique un total de anexos entre ${anexosRect.min || 0} y 200.`);
            return;
        }
        if (!checkRect.checked) {
            mostrarError(errorRect, "Debe confirmar la verificación física/File Server.");
            return;
        }

        guardarRect.disabled = true;
        mostrarError(errorRect, "");
        try {
            const respuesta = await fetch(rectificarUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    lote_id: loteId,
                    no_sp: sp,
                    total_folios: totalFolios,
                    total_anexos: totalAnexos,
                    confirmado: true,
                }),
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok) {
                mostrarError(errorRect, data.mensaje || "No fue posible guardar la rectificación.");
                return;
            }
            estadosSp.set(sp, data);
            filas().forEach((tr) => {
                if (tr.querySelector(".fila-sp").value.trim() === sp) estadoBadge(tr, data);
            });
            recalcularAnexos(sp);
            actualizarFilasPorSp(sp);
            cerrarModal(modalRect);
            mostrarError(errorGeneral, "");
        } catch (_error) {
            mostrarError(errorRect, "No fue posible guardar la rectificación. Revise la conexión.");
        } finally {
            guardarRect.disabled = false;
        }
    }

    function datosComunes() {
        return {
            tipo_referencia: document.getElementById("masivo-tipo-referencia").value,
            rc: document.getElementById("masivo-rc").value.trim(),
            providencia: document.getElementById("masivo-providencia").value.trim(),
            fecha_recepcion: document.getElementById("masivo-fecha").value,
            persona_entrega: document.getElementById("masivo-entrega").value.trim(),
        };
    }

    function prepararReportes() {
        filas().forEach((tr) => tr.classList.remove("fila-error"));
        const resultado = [];
        const repetidos = new Set();

        for (const tr of filas()) {
            if (!filaTieneDatos(tr)) continue;
            const noSp = tr.querySelector(".fila-sp").value.trim();
            const numeroReporte = tr.querySelector(".fila-reporte").value.trim();
            const tipoEvento = tr.querySelector(".fila-evento").value.trim();
            const folios = tr.querySelector(".fila-folios").value.trim();
            const modo = tr.querySelector(".fila-modo").value;
            const numeroAnexo = Number(tr.querySelector(".fila-anexo").value);
            const estado = estadoParaSp(noSp);

            let error = "";
            if (!noSp) error = "falta SP";
            else if (!numeroReporte) error = "falta número de reporte";
            else if (!tipoEvento) error = "falta tipo de evento";
            else if (!folios) error = "faltan folios";
            else if (!estado?.rectificado_lote) error = `el SP ${noSp} debe rectificarse`;
            else if (!Number.isInteger(numeroAnexo) || numeroAnexo < 1 || numeroAnexo > 200) error = "anexo no válido";
            else if (modo === "vencido" && numeroAnexo > Number(estado.anexos_rectificados)) {
                error = `el anexo vencido debe estar entre 1 y ${estado.anexos_rectificados}`;
            }

            const clave = `${noSp.toUpperCase()}|${numeroReporte.toUpperCase()}`;
            if (!error && repetidos.has(clave)) error = "reporte repetido dentro del lote";
            repetidos.add(clave);

            if (error) {
                tr.classList.add("fila-error");
                throw new Error(`Fila ${tr.querySelector(".masivo-col-num").textContent}: ${error}.`);
            }

            resultado.push({
                no_sp: noSp,
                numero_reporte: numeroReporte,
                tipo_evento: tipoEvento,
                folios,
                es_vencido: modo === "vencido",
                numero_anexo: numeroAnexo,
            });
        }

        if (resultado.length === 0) throw new Error("Agregue al menos un reporte completo.");
        return resultado;
    }

    function abrirRevision() {
        mostrarError(errorGeneral, "");
        const comunes = datosComunes();
        if (!comunes.rc) {
            mostrarError(errorGeneral, "Ingrese la RC/RE compartida por el lote.");
            document.getElementById("masivo-rc").focus();
            return;
        }
        if (!comunes.providencia) {
            mostrarError(errorGeneral, "Ingrese la providencia compartida por el lote.");
            document.getElementById("masivo-providencia").focus();
            return;
        }
        if (!comunes.fecha_recepcion) {
            mostrarError(errorGeneral, "Ingrese la fecha de recibido.");
            document.getElementById("masivo-fecha").focus();
            return;
        }

        let reportes;
        try {
            reportes = prepararReportes();
        } catch (error) {
            mostrarError(errorGeneral, error.message);
            return;
        }

        revisionRc.textContent = `${comunes.tipo_referencia} ${comunes.rc}`;
        revisionProvidencia.textContent = comunes.providencia;
        revisionFecha.textContent = comunes.fecha_recepcion;
        revisionTotal.textContent = String(reportes.length);
        revisionFilas.innerHTML = "";

        reportes.forEach((item, i) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${i + 1}</td>
                <td>${escapar(item.no_sp)}</td>
                <td>${escapar(item.numero_reporte)}</td>
                <td>${escapar(item.tipo_evento)}</td>
                <td>${escapar(item.folios)}</td>
                <td>${item.numero_anexo}</td>
                <td>${item.es_vencido ? "VENCIDO / HISTÓRICO" : "Vigente"}</td>
            `;
            revisionFilas.appendChild(tr);
        });

        modalRevision.dataset.payload = JSON.stringify({ comunes, reportes });
        checkFinal.checked = false;
        botonConfirmar.disabled = true;
        mostrarError(errorRevision, "");
        abrirModal(modalRevision);
    }

    function escapar(valor) {
        const div = document.createElement("div");
        div.textContent = String(valor ?? "");
        return div.innerHTML;
    }

    async function confirmarLote() {
        if (!checkFinal.checked) return;
        const almacenado = modalRevision.dataset.payload;
        if (!almacenado) return;
        const { comunes, reportes } = JSON.parse(almacenado);

        botonConfirmar.disabled = true;
        volverEdicion.disabled = true;
        mostrarError(errorRevision, "");
        try {
            const respuesta = await fetch(guardarUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    lote_id: loteId,
                    confirmacion_final: true,
                    ...comunes,
                    reportes,
                }),
            });
            const data = await respuesta.json();
            if (!respuesta.ok || !data.ok) {
                mostrarError(errorRevision, data.mensaje || "No fue posible registrar el lote.");
                return;
            }

            cerrarModal(modalRevision);
            exitoTexto.textContent = `${data.cantidad} reporte(s) registrados correctamente`;
            exito.hidden = false;
            window.setTimeout(() => {
                window.location.assign(data.redirect_url);
            }, 650);
        } catch (_error) {
            mostrarError(errorRevision, "No fue posible registrar el lote. Revise la conexión con SICODE.");
        } finally {
            botonConfirmar.disabled = !checkFinal.checked;
            volverEdicion.disabled = false;
        }
    }

    instalarVistaCompacta();
    sincronizarAlturaViewport();
    window.addEventListener("resize", sincronizarAlturaViewport, { passive: true });

    botonAgregar.addEventListener("click", () => agregarFilas(1));
    botonAgregarDiez.addEventListener("click", () => agregarFilas(10));
    botonRevisar.addEventListener("click", abrirRevision);
    guardarRect.addEventListener("click", guardarRectificacion);
    cancelarRect.addEventListener("click", () => cerrarModal(modalRect));
    volverEdicion.addEventListener("click", () => cerrarModal(modalRevision));
    checkFinal.addEventListener("change", () => {
        botonConfirmar.disabled = !checkFinal.checked;
    });
    botonConfirmar.addEventListener("click", confirmarLote);

    [modalRect, modalRevision].forEach((modal) => {
        modal.addEventListener("click", (evento) => {
            if (evento.target === modal) cerrarModal(modal);
        });
    });
    document.addEventListener("keydown", (evento) => {
        if (evento.key !== "Escape") return;
        if (!modalRect.hidden) cerrarModal(modalRect);
        else if (!modalRevision.hidden) cerrarModal(modalRevision);
    });

    agregarFilas(10);
})();