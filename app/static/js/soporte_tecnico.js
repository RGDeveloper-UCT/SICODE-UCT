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
  const tipoEquipo = form.querySelector('#tipo_equipo');
  const tipoEquipoOtro = form.querySelector('[data-tipo-equipo-otro]');

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

  servicios.forEach((item) => item.addEventListener('change', actualizarSecciones));
  form.querySelectorAll('input[name$="_detalles"]').forEach((item) => item.addEventListener('change', actualizarOtrosDetalles));
  tipoEquipo?.addEventListener('change', actualizarOtroEquipo);
  selectEstado?.addEventListener('change', actualizarCierre);

  actualizarSecciones();
  actualizarOtrosDetalles();
  actualizarOtroEquipo();
  actualizarCierre();
})();
