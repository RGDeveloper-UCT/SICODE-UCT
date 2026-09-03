(() => {
    const raiz = document.querySelector('[data-anexos-inteligentes]');
    if (!raiz) return;

    const form = raiz.querySelector('[data-anexos-form]');
    const tipoCodigo = raiz.querySelector('[data-tipo-codigo]');
    const botonesTipo = [...raiz.querySelectorAll('[data-tipo]')];
    const categorias = [...raiz.querySelectorAll('[data-categoria]')];
    const filtros = [...raiz.querySelectorAll('[data-filtro-categoria]')];
    const buscar = raiz.querySelector('[data-buscar-anexo]');
    const sinResultados = raiz.querySelector('[data-sin-resultados]');
    const panelComponentes = raiz.querySelector('[data-panel-componentes]');
    const panelOtro = raiz.querySelector('[data-panel-otro]');
    const resumenSeleccion = raiz.querySelector('[data-seleccion-resumen]');
    const especialAviso = raiz.querySelector('[data-especial-aviso]');
    const especialContinuar = raiz.querySelector('[data-especial-continuar]');
    const formularioGenerico = raiz.querySelector('[data-formulario-generico]');
    const noSp = raiz.querySelector('[data-no-sp]');
    const numeroAnexo = raiz.querySelector('[data-numero-anexo]');
    const estadoSp = raiz.querySelector('[data-estado-sp]');
    const componentes = [...raiz.querySelectorAll('[data-componente]')];
    const tituloGenerado = raiz.querySelector('[data-titulo-generado]');
    const tituloOtro = raiz.querySelector('[data-titulo-otro]');
    const confirmacion = raiz.querySelector('[data-confirmacion-file-server]');
    const vencido = raiz.querySelector('[data-anexo-vencido]');
    const resumenFinal = raiz.querySelector('[data-resumen-final]');
    const botonGuardar = raiz.querySelector('[data-guardar-anexo]');
    const botonContinuar = raiz.querySelector('.anexos-continuar');
    let seleccionado = null;
    let categoriaActiva = 'TODOS';

    const quitarAcentos = (texto) => (texto || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

    function mostrarPaso(numero) {
        raiz.querySelectorAll('[data-paso]').forEach((paso) => {
            const activo = paso.dataset.paso === String(numero);
            paso.hidden = !activo;
            paso.classList.toggle('activo', activo);
        });
        raiz.querySelectorAll('[data-paso-indicador]').forEach((indicador) => {
            indicador.classList.toggle('activo', Number(indicador.dataset.pasoIndicador) <= Number(numero));
        });
        raiz.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function filtrar() {
        const texto = quitarAcentos(buscar?.value);
        let visibles = 0;
        categorias.forEach((categoria) => {
            const coincideCategoria = categoriaActiva === 'TODOS' || categoria.dataset.categoria === categoriaActiva;
            let tiposVisibles = 0;
            categoria.querySelectorAll('[data-tipo]').forEach((boton) => {
                const coincideTexto = !texto || quitarAcentos(boton.dataset.titulo).includes(texto);
                const visible = coincideCategoria && coincideTexto;
                boton.hidden = !visible;
                if (visible) tiposVisibles += 1;
            });
            categoria.hidden = tiposVisibles === 0;
            visibles += tiposVisibles;
        });
        if (sinResultados) sinResultados.hidden = visibles !== 0;
    }

    function actualizarTituloComponentes() {
        const nombres = componentes.filter((item) => item.checked).map((item) => item.dataset.etiqueta);
        let detalle = '';
        if (nombres.length === 1) detalle = nombres[0];
        else if (nombres.length === 2) detalle = nombres.join(' y ');
        else if (nombres.length > 2) detalle = `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
        tituloGenerado.textContent = detalle ? `Reemplazo de ${detalle}` : 'Seleccione al menos un componente';
    }

    function seleccionar(boton) {
        botonesTipo.forEach((item) => item.classList.remove('seleccionado'));
        boton.classList.add('seleccionado');
        seleccionado = {
            codigo: boton.dataset.tipo,
            titulo: boton.dataset.titulo,
            modo: boton.dataset.modo,
            categoria: boton.dataset.categoriaTitulo,
            urlEspecial: boton.dataset.urlEspecial || '',
        };
        tipoCodigo.value = seleccionado.codigo;
        botonContinuar.disabled = false;
    }

    function prepararPasoDos() {
        if (!seleccionado) return false;
        resumenSeleccion.textContent = `${seleccionado.categoria} · ${seleccionado.titulo}`;
        const especial = seleccionado.modo === 'especial';
        especialAviso.hidden = !especial;
        formularioGenerico.hidden = especial;
        panelComponentes.hidden = seleccionado.modo !== 'componentes';
        panelOtro.hidden = seleccionado.modo !== 'libre';
        if (especial) especialContinuar.href = seleccionado.urlEspecial;
        return true;
    }

    async function revisarSp() {
        const valor = (noSp.value || '').trim();
        if (!valor) {
            estadoSp.className = 'estado-sp-anexo';
            estadoSp.querySelector('strong').textContent = 'Seleccione un SP';
            estadoSp.querySelector('small').textContent = 'SICODE verificará la secuencia documental.';
            return;
        }
        estadoSp.className = 'estado-sp-anexo';
        estadoSp.querySelector('strong').textContent = 'Verificando SP…';
        estadoSp.querySelector('small').textContent = 'Consultando secuencia de anexos.';
        try {
            const url = `${raiz.dataset.estadoSpUrl}?no_sp=${encodeURIComponent(valor)}`;
            const respuesta = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            const datos = await respuesta.json();
            if (!respuesta.ok || !datos.ok) throw new Error(datos.mensaje || 'SP no localizado');
            if (datos.requiere_rectificacion) {
                estadoSp.className = 'estado-sp-anexo alerta';
                estadoSp.querySelector('strong').textContent = `SP ${datos.no_sp} · requiere rectificación`;
                estadoSp.querySelector('small').textContent = 'Rectifique el total actual de anexos antes de guardar.';
                return;
            }
            estadoSp.className = 'estado-sp-anexo ok';
            estadoSp.querySelector('strong').textContent = `SP ${datos.no_sp} · ${datos.total_rectificado ?? 0} anexo(s)`;
            estadoSp.querySelector('small').textContent = `Siguiente anexo vigente: ${datos.siguiente_anexo}`;
            if (!vencido.checked && datos.siguiente_anexo && !numeroAnexo.value) numeroAnexo.value = datos.siguiente_anexo;
        } catch (error) {
            estadoSp.className = 'estado-sp-anexo error';
            estadoSp.querySelector('strong').textContent = 'SP no localizado';
            estadoSp.querySelector('small').textContent = error.message || 'Verifique el número ingresado.';
        }
    }

    function validarPasoDos() {
        if (seleccionado?.modo === 'especial') {
            window.location.assign(seleccionado.urlEspecial);
            return false;
        }
        if (!noSp.value.trim()) {
            noSp.focus();
            noSp.setCustomValidity('Indique el No. de SP.');
            noSp.reportValidity();
            noSp.setCustomValidity('');
            return false;
        }
        if (!numeroAnexo.value || Number(numeroAnexo.value) < 1) {
            numeroAnexo.focus();
            numeroAnexo.setCustomValidity('Indique el número de anexo.');
            numeroAnexo.reportValidity();
            numeroAnexo.setCustomValidity('');
            return false;
        }
        if (seleccionado?.modo === 'componentes' && !componentes.some((item) => item.checked)) {
            panelComponentes.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return false;
        }
        if (seleccionado?.modo === 'libre' && !tituloOtro.value.trim()) {
            tituloOtro.focus();
            tituloOtro.setCustomValidity('Escriba el nombre del tipo de anexo.');
            tituloOtro.reportValidity();
            tituloOtro.setCustomValidity('');
            return false;
        }
        if (!confirmacion.checked) {
            confirmacion.focus();
            confirmacion.setCustomValidity('Debe confirmar el número contra File Server.');
            confirmacion.reportValidity();
            confirmacion.setCustomValidity('');
            return false;
        }
        return true;
    }

    function valorCampo(nombre) {
        const campo = form.elements.namedItem(nombre);
        return campo && 'value' in campo ? (campo.value || '').trim() : '';
    }

    function construirResumen() {
        const titulo = seleccionado.modo === 'componentes' ? tituloGenerado.textContent : (seleccionado.modo === 'libre' ? tituloOtro.value.trim() : seleccionado.titulo);
        const ref = `${valorCampo('tipo_referencia')} ${valorCampo('rc')}`.trim();
        const datos = [
            ['Tipo de anexo', titulo],
            ['Categoría', seleccionado.categoria],
            ['SP', noSp.value.trim()],
            ['Anexo No.', numeroAnexo.value],
            ['Referencia', ref === valorCampo('tipo_referencia') ? '—' : ref],
            ['Providencia', valorCampo('providencia') || '—'],
            ['Fecha recibido', valorCampo('fecha_recepcion') || '—'],
            ['Folios', valorCampo('folios') || '—'],
            ['Entrega / remite', valorCampo('persona_entrega') || '—'],
            ['Condición', vencido.checked ? 'Vencido / histórico' : 'Vigente'],
        ];
        resumenFinal.innerHTML = datos.map(([etiqueta, valor]) => `<div class="resumen-dato"><span>${etiqueta}</span><strong>${escapeHtml(valor)}</strong></div>`).join('');
    }

    function escapeHtml(texto) {
        const elemento = document.createElement('div');
        elemento.textContent = texto;
        return elemento.innerHTML;
    }

    botonesTipo.forEach((boton) => boton.addEventListener('click', () => seleccionar(boton)));
    filtros.forEach((boton) => boton.addEventListener('click', () => {
        categoriaActiva = boton.dataset.filtroCategoria;
        filtros.forEach((item) => item.classList.toggle('activo', item === boton));
        filtrar();
    }));
    buscar?.addEventListener('input', filtrar);
    componentes.forEach((item) => item.addEventListener('change', actualizarTituloComponentes));
    noSp?.addEventListener('change', revisarSp);
    noSp?.addEventListener('blur', revisarSp);
    vencido?.addEventListener('change', () => { if (!vencido.checked) revisarSp(); });

    raiz.querySelectorAll('[data-ir-paso]').forEach((boton) => boton.addEventListener('click', () => {
        const destino = Number(boton.dataset.irPaso);
        if (destino === 2 && !prepararPasoDos()) return;
        if (destino === 3) {
            if (!validarPasoDos()) return;
            construirResumen();
        }
        mostrarPaso(destino);
    }));

    especialContinuar?.addEventListener('click', (evento) => {
        if (!seleccionado?.urlEspecial) evento.preventDefault();
    });

    form.addEventListener('submit', (evento) => {
        if (!validarPasoDos()) {
            evento.preventDefault();
            mostrarPaso(2);
            return;
        }
        botonGuardar?.classList.add('cargando');
        if (botonGuardar) botonGuardar.disabled = true;
    });
})();
