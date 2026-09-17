(() => {
    const raiz = document.querySelector('[data-riesgo-masivo]');
    if (!raiz) return;

    const cuerpo = raiz.querySelector('[data-filas-riesgo]');
    const plantilla = document.getElementById('plantilla-fila-riesgo');
    const botonAgregar = raiz.querySelector('[data-agregar-fila]');
    const botonValidar = raiz.querySelector('[data-validar-lote]');
    const botonGuardar = raiz.querySelector('[data-guardar-lote]');
    const botonLimpiar = raiz.querySelector('[data-limpiar-lote]');
    const confirmacionGeneral = raiz.querySelector('[data-confirmacion-file-server]');
    const resultadoLote = raiz.querySelector('[data-resultado-lote]');
    const totalFilas = raiz.querySelector('[data-total-filas]');
    const totalValidas = raiz.querySelector('[data-total-validas]');
    const totalErrores = raiz.querySelector('[data-total-errores]');
    const totalRectificar = raiz.querySelector('[data-total-rectificar]');
    const maxFilas = Number(raiz.dataset.maxFilas || 100);
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

    const dialogoHistorico = document.querySelector('[data-dialogo-historico]');
    const historicoContexto = dialogoHistorico?.querySelector('[data-historico-contexto]');
    const historicoNumero = dialogoHistorico?.querySelector('[data-historico-numero]');
    const historicoConfirmacion = dialogoHistorico?.querySelector('[data-historico-confirmacion]');

    const dialogoRectificar = document.querySelector('[data-dialogo-rectificar]');
    const rectificarContexto = dialogoRectificar?.querySelector('[data-rectificar-contexto]');
    const rectificarTotal = dialogoRectificar?.querySelector('[data-rectificar-total]');
    const rectificarConfirmacion = dialogoRectificar?.querySelector('[data-rectificar-confirmacion]');

    let consecutivo = 0;
    let filaHistorico = null;
    let filaRectificar = null;
    let resultadoRectificar = null;
    let ultimaValidacion = new Map();

    function mostrarMensaje(texto, tipo = '') {
        resultadoLote.hidden = !texto;
        resultadoLote.textContent = texto || '';
        resultadoLote.className = `riesgo-masivo__resultado${tipo ? ` ${tipo}` : ''}`;
    }

    function filasDom() {
        return [...cuerpo.querySelectorAll('[data-fila-riesgo]')];
    }

    function renumerar() {
        filasDom().forEach((fila, indice) => {
            fila.querySelector('[data-numero-fila]').textContent = String(indice + 1);
        });
        actualizarResumen();
    }

    function filaTieneDatos(fila) {
        return Boolean(
            fila.querySelector('[data-fecha-recibido]').value
            || fila.querySelector('[data-correlativo]').value.trim()
            || fila.querySelector('[data-no-sp]').value.trim()
        );
    }

    function serializarFila(fila) {
        return {
            id: fila.dataset.filaId,
            fecha_recepcion: fila.querySelector('[data-fecha-recibido]').value,
            correlativo: fila.querySelector('[data-correlativo]').value.trim(),
            no_sp: fila.querySelector('[data-no-sp]').value.trim(),
            es_vencido: fila.dataset.esVencido === '1',
            numero_anexo: fila.dataset.numeroAnexo || null,
        };
    }

    function obtenerFilasCapturadas() {
        return filasDom().filter(filaTieneDatos).map(serializarFila);
    }

    function invalidarFila(fila) {
        ultimaValidacion.delete(fila.dataset.filaId);
        fila.classList.remove('fila-valida', 'fila-error', 'fila-rectificacion');
        const estado = fila.querySelector('[data-estado-fila]');
        estado.replaceChildren();
        const badge = document.createElement('span');
        badge.className = 'riesgo-masivo__badge';
        badge.textContent = 'Sin validar';
        const detalle = document.createElement('small');
        detalle.textContent = 'Los datos cambiaron. Valide nuevamente el lote.';
        estado.append(badge, detalle);
        renderAcciones(fila, null);
        actualizarResumen();
    }

    function crearBoton(texto, onClick, clase = '') {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = `riesgo-masivo__mini${clase ? ` ${clase}` : ''}`;
        boton.textContent = texto;
        boton.addEventListener('click', onClick);
        return boton;
    }

    function renderAcciones(fila, resultado) {
        const contenedor = fila.querySelector('[data-acciones-fila]');
        contenedor.replaceChildren();

        if (resultado?.estado === 'rectificacion') {
            contenedor.appendChild(crearBoton('Rectificar SP', () => abrirRectificacion(fila, resultado)));
        } else if (resultado?.valido) {
            if (resultado.es_vencido) {
                contenedor.appendChild(crearBoton('Usar como nuevo', () => {
                    fila.dataset.esVencido = '0';
                    fila.dataset.numeroAnexo = '';
                    validarLote();
                }));
            } else {
                contenedor.appendChild(crearBoton('Es histórico', () => abrirHistorico(fila, resultado)));
            }
        } else if (filaTieneDatos(fila)) {
            contenedor.appendChild(crearBoton('Revalidar', validarLote));
        }

        contenedor.appendChild(crearBoton('Eliminar', () => {
            fila.remove();
            if (!filasDom().length) agregarFila();
            renumerar();
        }, 'peligro'));
    }

    function agregarFila(datos = {}) {
        if (filasDom().length >= maxFilas) {
            mostrarMensaje(`El lote admite como máximo ${maxFilas} filas.`, 'error');
            return null;
        }

        consecutivo += 1;
        const fragmento = plantilla.content.cloneNode(true);
        const fila = fragmento.querySelector('[data-fila-riesgo]');
        fila.dataset.filaId = datos.id || `fila-${Date.now()}-${consecutivo}`;
        fila.dataset.esVencido = datos.es_vencido ? '1' : '0';
        fila.dataset.numeroAnexo = datos.numero_anexo || '';
        fila.querySelector('[data-fecha-recibido]').value = datos.fecha_recepcion || '';
        fila.querySelector('[data-correlativo]').value = datos.correlativo || '';
        fila.querySelector('[data-no-sp]').value = datos.no_sp || '';

        fila.querySelectorAll('input').forEach((input) => {
            input.addEventListener('input', () => invalidarFila(fila));
            input.addEventListener('change', () => invalidarFila(fila));
        });

        cuerpo.appendChild(fila);
        renderAcciones(fila, null);
        renumerar();
        return fila;
    }

    function aplicarResultado(fila, resultado) {
        ultimaValidacion.set(fila.dataset.filaId, resultado);
        fila.classList.remove('fila-valida', 'fila-error', 'fila-rectificacion');

        if (resultado.valido) fila.classList.add('fila-valida');
        else if (resultado.estado === 'rectificacion') fila.classList.add('fila-rectificacion');
        else fila.classList.add('fila-error');

        const estado = fila.querySelector('[data-estado-fila]');
        estado.replaceChildren();

        const badge = document.createElement('span');
        badge.className = 'riesgo-masivo__badge';
        if (resultado.valido) {
            badge.classList.add('ok');
            badge.textContent = resultado.es_vencido ? 'Histórico' : 'Nuevo';
        } else if (resultado.estado === 'rectificacion') {
            badge.classList.add('alerta');
            badge.textContent = 'Rectificar';
        } else {
            badge.classList.add('error');
            badge.textContent = 'Error';
        }

        const titulo = document.createElement('strong');
        titulo.textContent = resultado.numero_anexo
            ? `Anexo ${resultado.numero_anexo} · ${resultado.condicion || ''}`
            : (resultado.no_sp ? `SP ${resultado.no_sp}` : 'Registro no válido');

        const detalle = document.createElement('small');
        detalle.textContent = resultado.mensaje || '';

        estado.append(badge, titulo, detalle);
        renderAcciones(fila, resultado);
    }

    function aplicarResultados(resultados) {
        const porId = new Map((resultados || []).map((item) => [String(item.id), item]));
        filasDom().forEach((fila) => {
            const resultado = porId.get(fila.dataset.filaId);
            if (resultado) aplicarResultado(fila, resultado);
        });
        actualizarResumen();
    }

    function actualizarResumen() {
        const capturadas = filasDom().filter(filaTieneDatos).length;
        const resultados = [...ultimaValidacion.values()];
        const validas = resultados.filter((item) => item.valido).length;
        const rectificar = resultados.filter((item) => item.estado === 'rectificacion').length;
        const errores = resultados.filter((item) => !item.valido && item.estado !== 'rectificacion').length;

        totalFilas.textContent = String(capturadas);
        totalValidas.textContent = String(validas);
        totalErrores.textContent = String(errores);
        totalRectificar.textContent = String(rectificar);
        botonGuardar.disabled = validas === 0;
    }

    async function postJson(url, payload) {
        const respuesta = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                'X-CSRFToken': csrf,
            },
            body: JSON.stringify(payload),
        });
        let datos = {};
        try {
            datos = await respuesta.json();
        } catch (_error) {
            datos = { ok: false, mensaje: 'El servidor devolvió una respuesta no válida.' };
        }
        if (!respuesta.ok) {
            const error = new Error(datos.mensaje || 'No fue posible completar la operación.');
            error.datos = datos;
            throw error;
        }
        return datos;
    }

    async function validarLote() {
        const filas = obtenerFilasCapturadas();
        if (!filas.length) {
            mostrarMensaje('Capture al menos una fila antes de validar.', 'error');
            return;
        }

        botonValidar.disabled = true;
        botonGuardar.disabled = true;
        mostrarMensaje('Validando SP, correlativos y secuencia de anexos…');
        try {
            const datos = await postJson(raiz.dataset.urlValidar, { filas });
            aplicarResultados(datos.resultados);
            mostrarMensaje(
                `Validación terminada: ${datos.validos} fila(s) lista(s), ${datos.errores} pendiente(s) y ${datos.rectificaciones} SP por rectificar.`,
                datos.errores === 0 ? 'ok' : ''
            );
        } catch (error) {
            if (error.datos?.resultados) aplicarResultados(error.datos.resultados);
            mostrarMensaje(error.message, 'error');
        } finally {
            botonValidar.disabled = false;
            actualizarResumen();
        }
    }

    function abrirHistorico(fila, resultado) {
        filaHistorico = fila;
        historicoContexto.textContent = (
            `SP ${resultado.no_sp}. La secuencia vigente rectificada es ${resultado.total_rectificado ?? 0}. `
            + 'Indique el número físico original que aparece en File Server.'
        );
        historicoNumero.value = fila.dataset.numeroAnexo || '';
        historicoConfirmacion.checked = false;
        dialogoHistorico.showModal();
        historicoNumero.focus();
    }

    function cerrarHistorico() {
        filaHistorico = null;
        dialogoHistorico.close();
    }

    function confirmarHistorico() {
        if (!filaHistorico) return;
        const numero = Number(historicoNumero.value);
        if (!Number.isInteger(numero) || numero < 1 || numero > 200) {
            historicoNumero.focus();
            historicoNumero.setCustomValidity('Indique un número de anexo válido.');
            historicoNumero.reportValidity();
            historicoNumero.setCustomValidity('');
            return;
        }
        if (!historicoConfirmacion.checked) {
            historicoConfirmacion.focus();
            historicoConfirmacion.setCustomValidity('Confirme el número contra File Server.');
            historicoConfirmacion.reportValidity();
            historicoConfirmacion.setCustomValidity('');
            return;
        }
        filaHistorico.dataset.esVencido = '1';
        filaHistorico.dataset.numeroAnexo = String(numero);
        dialogoHistorico.close();
        filaHistorico = null;
        validarLote();
    }

    function abrirRectificacion(fila, resultado) {
        filaRectificar = fila;
        resultadoRectificar = resultado;
        rectificarContexto.textContent = (
            `SP ${resultado.no_sp}. SICODE conoce al menos ${resultado.minimo_conocido ?? 0} anexo(s). `
            + 'Confirme en File Server el total real antes de actualizar.'
        );
        rectificarTotal.min = String(resultado.minimo_conocido ?? 0);
        rectificarTotal.value = resultado.total_rectificado ?? resultado.minimo_conocido ?? 0;
        rectificarConfirmacion.checked = false;
        dialogoRectificar.showModal();
        rectificarTotal.focus();
    }

    function cerrarRectificacion() {
        filaRectificar = null;
        resultadoRectificar = null;
        dialogoRectificar.close();
    }

    async function confirmarRectificacion() {
        if (!filaRectificar || !resultadoRectificar) return;
        const total = Number(rectificarTotal.value);
        const minimo = Number(resultadoRectificar.minimo_conocido || 0);
        if (!Number.isInteger(total) || total < minimo || total > 200) {
            rectificarTotal.focus();
            rectificarTotal.setCustomValidity(`Indique un total entre ${minimo} y 200.`);
            rectificarTotal.reportValidity();
            rectificarTotal.setCustomValidity('');
            return;
        }
        if (!rectificarConfirmacion.checked) {
            rectificarConfirmacion.focus();
            rectificarConfirmacion.setCustomValidity('Confirme la verificación contra File Server.');
            rectificarConfirmacion.reportValidity();
            rectificarConfirmacion.setCustomValidity('');
            return;
        }

        const boton = dialogoRectificar.querySelector('[data-confirmar-rectificar]');
        boton.disabled = true;
        try {
            await postJson(raiz.dataset.urlRectificar, {
                expediente_id: resultadoRectificar.expediente_id,
                total_anexos: total,
            });
            cerrarRectificacion();
            await validarLote();
        } catch (error) {
            mostrarMensaje(error.message, 'error');
        } finally {
            boton.disabled = false;
        }
    }

    async function guardarLote() {
        const filas = obtenerFilasCapturadas();
        if (!filas.length) {
            mostrarMensaje('No hay filas para guardar.', 'error');
            return;
        }
        if (!confirmacionGeneral.checked) {
            confirmacionGeneral.focus();
            confirmacionGeneral.setCustomValidity('Confirme la revisión de secuencia contra File Server.');
            confirmacionGeneral.reportValidity();
            confirmacionGeneral.setCustomValidity('');
            return;
        }

        botonGuardar.disabled = true;
        botonValidar.disabled = true;
        mostrarMensaje('Guardando filas válidas y registrando bitácora…');
        try {
            const datos = await postJson(raiz.dataset.urlGuardar, {
                filas,
                confirmacion_file_server: true,
            });

            const guardados = new Set((datos.guardados || []).map(String));
            filasDom().forEach((fila) => {
                if (guardados.has(fila.dataset.filaId)) fila.remove();
            });

            ultimaValidacion = new Map();
            if (!filasDom().length) agregarFila();
            if (datos.resultados?.length) aplicarResultados(datos.resultados);
            renumerar();
            confirmacionGeneral.checked = false;
            mostrarMensaje(datos.mensaje, 'ok');
        } catch (error) {
            if (error.datos?.resultados) aplicarResultados(error.datos.resultados);
            mostrarMensaje(error.message, 'error');
        } finally {
            botonValidar.disabled = false;
            actualizarResumen();
        }
    }

    function limpiarLote() {
        if (obtenerFilasCapturadas().length && !window.confirm('¿Limpiar todas las filas capturadas?')) return;
        cuerpo.replaceChildren();
        ultimaValidacion = new Map();
        confirmacionGeneral.checked = false;
        mostrarMensaje('');
        agregarFila();
        agregarFila();
        agregarFila();
    }

    botonAgregar.addEventListener('click', () => agregarFila());
    botonValidar.addEventListener('click', validarLote);
    botonGuardar.addEventListener('click', guardarLote);
    botonLimpiar.addEventListener('click', limpiarLote);

    document.querySelector('[data-cerrar-historico]')?.addEventListener('click', cerrarHistorico);
    document.querySelector('[data-confirmar-historico]')?.addEventListener('click', confirmarHistorico);
    document.querySelector('[data-cerrar-rectificar]')?.addEventListener('click', cerrarRectificacion);
    document.querySelector('[data-confirmar-rectificar]')?.addEventListener('click', confirmarRectificacion);

    dialogoHistorico?.addEventListener('cancel', (evento) => {
        evento.preventDefault();
        cerrarHistorico();
    });
    dialogoRectificar?.addEventListener('cancel', (evento) => {
        evento.preventDefault();
        cerrarRectificacion();
    });

    for (let i = 0; i < 5; i += 1) agregarFila();
})();
