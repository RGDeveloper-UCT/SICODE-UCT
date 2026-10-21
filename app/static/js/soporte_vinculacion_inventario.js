/* Vinculación del personal con el inventario maestro de Control 09. */
(() => {
  const form = document.querySelector('form.soporte-form');
  if (!form) return;
  const personal = form.querySelector('#personal_institucional_id');
  const equipo = form.querySelector('#equipo_institucional_id');
  const busqueda = form.querySelector('#buscar_equipo_inventario');
  const aviso = document.getElementById('mensaje-equipo-asignado');
  const tipos = {COMPUTADORA:'PC', PORTATIL:'LAPTOP', IMPRESORA:'IMPRESORA', ESCANER:'ESCANER'};
  const campo = nombre => form.elements.namedItem(nombre);
  const escribir = (nombre, valor) => {
    const item = campo(nombre);
    if (!item) return;
    item.value = valor || '';
    item.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const mostrar = (id, valor) => {
    const el = document.getElementById(id);
    if (el) el.value = valor || '';
  };
  const texto = value => String(value || '').trim().toLocaleLowerCase('es');
  const opciones = () => [...(equipo?.options || [])].filter(o => o.value && o.value !== '0');
  function datosEquipo() {
    const o = equipo?.selectedOptions[0];
    return o?.value && o.value !== '0' ? o.dataset : null;
  }
  function actualizarFicha() {
    const d = datosEquipo();
    escribir('inventario', d?.sicoin);
    escribir('numero_serie', d?.serie);
    escribir('marca_modelo', d?.marca);
    escribir('ip_nombre_equipo', d ? (d.ip || d.nombre) : '');
    escribir('tipo_equipo', d ? (tipos[d.tipo] || 'OTRO') : '');
    escribir('tipo_equipo_otro', d && !tipos[d.tipo] ? d.tipo : '');
    mostrar('inventario_area', d?.area);
    mostrar('inventario_ubicacion', d?.ubicacion);
    mostrar('inventario_custodio', d?.custodio);
    mostrar('inventario_habitual', d?.usuario);
    mostrar('inventario_acceso', d ? [d.acceso, d.tipoAcceso].filter(Boolean).join(' · ') : '');
    mostrar('inventario_estado', d?.estado);
    if (d && aviso) aviso.textContent = 'Equipo vinculado: ' + (d.sicoin || 'Sin SICOIN') + ' — ' + (d.nombre || '');
  }
  function filtrarBusqueda() {
    const q = texto(busqueda?.value);
    for (const o of opciones()) o.hidden = !!q && !texto(o.textContent + ' ' + (o.dataset.serie || '')).includes(q);
  }
  function actualizarPorPersonal() {
    const p = personal?.selectedOptions[0];
    const id = personal?.value;
    if (p && id && id !== '0') {
      escribir('usuario_solicitante', p.dataset.nombre);
      escribir('coordinacion_area', p.dataset.area);
      escribir('nombre_firma_usuario', p.dataset.nombre);
    }
    const asignados = opciones().filter(o => id && id !== '0' &&
      (o.dataset.habitualId === id || o.dataset.custodioId === id));
    if (busqueda) busqueda.value = '';
    for (const o of opciones()) o.hidden = Boolean(asignados.length && !asignados.includes(o));
    if (asignados.length === 1) {
      equipo.value = asignados[0].value;
      actualizarFicha();
    } else {
      equipo.value = '0';
      actualizarFicha();
      if (aviso) aviso.textContent = asignados.length > 1
        ? 'Se encontraron ' + asignados.length + ' equipos asignados. Seleccione el que recibió atención.'
        : 'No hay equipos asignados a esta persona. Puede buscar uno manualmente.';
    }
  }
  equipo?.addEventListener('change', actualizarFicha);
  personal?.addEventListener('change', actualizarPorPersonal);
  busqueda?.addEventListener('input', () => {
    // La búsqueda manual siempre permite encontrar equipos del inventario completo.
    for (const o of opciones()) o.hidden = false;
    filtrarBusqueda();
    if (equipo?.selectedOptions[0]?.hidden) {
      equipo.value = '0';
      actualizarFicha();
    }
  });
  // En edición y al recuperar un borrador, respetar el equipo guardado.
  if (equipo?.value && equipo.value !== '0') actualizarFicha();
  else if (personal?.value && personal.value !== '0') actualizarPorPersonal();
})();
