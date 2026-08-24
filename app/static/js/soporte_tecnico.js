(() => {
  const form = document.querySelector('[data-soporte-form]');
  if (!form) return;

  const servicios = [...form.querySelectorAll('input[name="tipos_servicio"]')];
  const secciones = [...form.querySelectorAll('[data-soporte-section]')];
  const equipo = form.querySelector('[data-equipo-section]');
  const resumenServicio = form.querySelector('[data-resumen-servicio]');
  const resumenEstado = form.querySelector('[data-resumen-estado]');
  const selectEstado = form.querySelector('[data-estado-final]');
  const fechaCierre = form.querySelector('[data-fecha-cierre]');
  const tiempoResolucion = form.querySelector('#tiempo_empleado');
  const tipoEquipo = form.querySelector('#tipo_equipo');
  const tipoEquipoOtro = form.querySelector('[data-tipo-equipo-otro]');
  const minimizarLinks = [...document.querySelectorAll('[data-minimizar-ticket]')];
  const cancelarLinks = [...document.querySelectorAll('[data-cancelar-ticket]')];
  const avisos = [...document.querySelectorAll('[data-soporte-toast]')];
  const ticketApi = window.SICODETicketSoporte;

  const necesitaEquipo = new Set(['HARDWARE', 'SOFTWARE', 'INSTALACION', 'TRASLADO', 'REVISION']);

  function seleccionados() {
    return servicios.filter((item) => item.checked).map((item) => item.value);
  }

  function etiquetasSeleccionadas() {
    return servicios
      .filter((item) => item.checked)
      .map((item) => item.closest('label')?.querySelector('span')?.textContent?.trim() || item.value);
  }

  function actualizarSecciones() {
    const activos = new Set(seleccionados());
    secciones.forEach((seccion) => {
      const codigo = seccion.dataset.soporteSection;
      seccion.hidden = !activos.has(codigo);
    });
    if (equipo) equipo.hidden = ![...activos].some((codigo) => necesitaEquipo.has(codigo));

    const etiquetas = etiquetasSeleccionadas();
    if (resumenServicio) {
      resumenServicio.textContent = etiquetas.length
        ? etiquetas.join(' · ')
        : 'Seleccione el tipo de servicio';
    }
  }

  function actualizarOtroEquipo() {
    if (!tipoEquipoOtro || !tipoEquipo) return;
    tipoEquipoOtro.hidden = tipoEquipo.value !== 'OTRO';
  }

  function actualizarOtrosDetalles() {
    ['instalacion', 'traslado', 'revision'].forEach((grupo) => {
      const contenedor = form.querySelector(`[data-otro-detalle="${grupo}"]`);
      if (!contenedor) return;
      const nombre = `${grupo}_detalles`;
      const marcado = [...form.querySelectorAll(`input[name="${nombre}"]`)]
        .some((item) => item.checked && item.value === 'OTRO');
      contenedor.hidden = !marcado;
    });
  }

  function fechaHoraLocalActual() {
    const ahora = new Date();
    const desplazamiento = ahora.getTimezoneOffset();
    return new Date(ahora.getTime() - desplazamiento * 60000).toISOString().slice(0, 16);
  }

  function actualizarCierre() {
    if (!selectEstado) return;
    const texto = selectEstado.options[selectEstado.selectedIndex]?.text || selectEstado.value;
    if (resumenEstado) resumenEstado.textContent = `Estado: ${texto}`;
    if (selectEstado.value !== 'PENDIENTE' && fechaCierre && !fechaCierre.value) {
      fechaCierre.value = fechaHoraLocalActual();
    }
  }

  function currentTicketMatches(ticket) {
    if (!ticket) return false;
    const current = window.location.pathname;
    const resume = ticket.resumeUrl || '/coordinacion/soporte-tecnico/nuevo';
    return current === resume || (current.endsWith('/nuevo') && resume.endsWith('/nuevo'));
  }

  function serializeDraft() {
    const draft = {};
    const fields = [...form.elements].filter((field) => field.name && !['csrf_token', 'submit'].includes(field.name));
    fields.forEach((field) => {
      if (field.type === 'checkbox' || field.type === 'radio') {
        if (!draft[field.name]) draft[field.name] = [];
        if (field.checked) draft[field.name].push(field.value);
      } else {
        draft[field.name] = field.value;
      }
    });
    return draft;
  }

  function restoreDraft(draft) {
    if (!draft || typeof draft !== 'object') return;
    Object.entries(draft).forEach(([name, value]) => {
      const fields = [...form.querySelectorAll(`[name="${CSS.escape(name)}"]`)];
      fields.forEach((field) => {
        if (field.type === 'checkbox' || field.type === 'radio') {
          field.checked = Array.isArray(value) && value.includes(field.value);
        } else if (typeof value === 'string') {
          field.value = value;
        }
      });
    });
  }

  function saveDraft() {
    if (!ticketApi) return;
    const ticket = ticketApi.read();
    if (!currentTicketMatches(ticket)) return;
    ticket.draft = serializeDraft();
    ticket.label = etiquetasSeleccionadas()[0] || 'Tiempo de resolución';
    ticketApi.write(ticket);
  }

  function updateTimerField() {
    if (!ticketApi || !tiempoResolucion) return;
    const ticket = ticketApi.read();
    if (!currentTicketMatches(ticket)) return;
    tiempoResolucion.value = ticketApi.formatDuration(ticketApi.elapsed(ticket));
    tiempoResolucion.readOnly = true;
    tiempoResolucion.title = 'Calculado automáticamente desde que se inició el ticket.';
  }

  function cerrarAviso(aviso) {
    if (!aviso || aviso.dataset.cerrando === '1') return;
    aviso.dataset.cerrando = '1';
    aviso.classList.add('soporte-toast-saliendo');
    window.setTimeout(() => aviso.remove(), 220);
  }

  avisos.forEach((aviso, indice) => {
    aviso.querySelector('[data-soporte-toast-cerrar]')?.addEventListener('click', () => cerrarAviso(aviso));
    window.setTimeout(() => cerrarAviso(aviso), 60000 + (indice * 350));
  });

  const activeTicket = ticketApi?.read();
  if (currentTicketMatches(activeTicket)) {
    if (activeTicket.draft && Object.keys(activeTicket.draft).length) {
      restoreDraft(activeTicket.draft);
    }
    updateTimerField();
    window.setInterval(updateTimerField, 1000);
  }

  servicios.forEach((item) => item.addEventListener('change', actualizarSecciones));
  form.querySelectorAll('input[name$="_detalles"]').forEach((item) => item.addEventListener('change', actualizarOtrosDetalles));
  tipoEquipo?.addEventListener('change', actualizarOtroEquipo);
  selectEstado?.addEventListener('change', actualizarCierre);

  form.addEventListener('input', saveDraft);
  form.addEventListener('change', saveDraft);
  window.addEventListener('pagehide', saveDraft);

  minimizarLinks.forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      saveDraft();
      window.location.href = link.href;
    });
  });

  cancelarLinks.forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      const confirmar = window.confirm(
        '¿Cancelar esta boleta de soporte? Se detendrá el cronómetro y se descartarán los datos no guardados.'
      );
      if (!confirmar) return;
      ticketApi?.clear();
      window.location.href = link.href;
    });
  });

  form.addEventListener('submit', () => {
    if (!ticketApi) return;
    const ticket = ticketApi.read();
    if (!currentTicketMatches(ticket)) return;
    updateTimerField();
    saveDraft();
    const refreshed = ticketApi.read();
    if (!refreshed) return;
    refreshed.pendingSubmitState = selectEstado?.value || 'PENDIENTE';
    ticketApi.write(refreshed);
  });

  actualizarSecciones();
  actualizarOtrosDetalles();
  actualizarOtroEquipo();
  actualizarCierre();
  saveDraft();
})();
