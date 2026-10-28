(() => {
  const root = document.querySelector('[data-nexo]');
  if (!root) return;

  const $ = (s) => root.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const nombresEtapa = {
    postgresql: 'conexión con PostgreSQL',
    aprendizaje: 'aprendizaje de verificaciones',
    inventario_esquema: 'inventario del esquema',
    analisis_sicode: 'análisis transversal',
    guardar_hallazgos: 'registro de hallazgos',
  };

  function actualizarConexion(nombre, info) {
    if (!info) return;
    const filas = [...root.querySelectorAll('.connections > div')];
    const fila = filas.find(x => x.querySelector('b')?.textContent?.trim() === nombre);
    if (!fila) return;

    const dot = fila.querySelector('.connection-dot');
    if (dot) {
      dot.className = 'connection-dot';
      if (info.disponible === true) dot.classList.add('active');
      if (info.disponible === null) dot.classList.add('neutral');
    }

    const small = fila.querySelector('small');
    if (!small) return;
    if (nombre === 'Ollama') {
      small.textContent = info.disponible
        ? `IA local activa · ${info.modelo || 'modelo local'}`
        : 'IA local no disponible en este momento';
      return;
    }
    if (nombre === 'PostgreSQL') {
      small.textContent = info.disponible ? 'Núcleo de datos conectado' : 'Conexión con la base de datos no disponible';
      return;
    }
    small.textContent = info.nota || info.modo || small.textContent;
  }

  function renderHallazgos(data) {
    const list = $('[data-findings]');
    if (!list) return;

    const hallazgos = data.hallazgos || [];
    const diagnostico = data.diagnostico || {};
    const etapas = diagnostico.etapas_con_error || [];
    const bloques = [];

    if (diagnostico.degradado) {
      const nombres = etapas.length
        ? etapas.map(etapa => nombresEtapa[etapa] || etapa).join(', ')
        : 'una etapa interna';
      bloques.push(`
        <div class="finding alta">
          <b>Análisis parcial · NEXO sigue operativo</b>
          <p>No se completó ${esc(nombres)}. Las demás comprobaciones continúan disponibles y el detalle técnico quedó registrado en el servidor.</p>
          <small><strong>Acción:</strong> actualice la aplicación y migraciones; si persiste, revise <code>journalctl -u sicode.service</code>.</small>
        </div>`);
    }

    if (!hallazgos.length && !diagnostico.degradado) {
      bloques.push('<div class="finding baja"><b>Sin hallazgos prioritarios</b><p>NEXO no detectó patrones que requieran atención en este análisis.</p></div>');
    } else {
      bloques.push(...hallazgos.map(h => `
        <article class="finding ${esc(h.prioridad || 'media')}">
          <b>${esc(h.titulo || 'Hallazgo')}</b>
          <p>${esc(h.detalle || '')}</p>
          ${h.recomendacion ? `<small><strong>Recomendación:</strong> ${esc(h.recomendacion)}</small>` : ''}
        </article>`));
    }

    list.innerHTML = bloques.join('');
  }

  async function cargar() {
    const status = $('[data-nexo-status]');
    const btn = $('[data-refresh]');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);

    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Analizando SICODE…';

    try {
      const response = await fetch(root.dataset.url, {
        headers: {'Accept': 'application/json'},
        signal: controller.signal,
        cache: 'no-store',
      });

      let data = null;
      try {
        data = await response.json();
      } catch (_) {
        data = null;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!data || typeof data !== 'object') throw new Error('Respuesta JSON inválida');

      const aprendizaje = data.aprendizaje || {};
      const totales = data.totales || {};
      const hallazgos = data.hallazgos || [];

      $('[data-kpi-level]').textContent = `${aprendizaje.nivel || 0}%`;
      $('[data-kpi-samples]').textContent = aprendizaje.muestras || 0;
      $('[data-kpi-precision]').textContent = `${aprendizaje.precision || 0}%`;
      $('[data-kpi-findings]').textContent = data.hallazgos_total || hallazgos.length || 0;
      $('[data-kpi-objects]').textContent = (totales.objetos_estudiados || 0).toLocaleString('es-GT');
      $('[data-meter]').style.width = `${Math.max(2, Math.min(100, aprendizaje.nivel || 0))}%`;

      if (status) {
        if (data.estado === 'degradado') {
          status.textContent = 'NEXO activo · análisis parcial con diagnóstico';
        } else if (data.estado === 'requiere_revision') {
          status.textContent = 'Análisis completo · hay hallazgos para revisar';
        } else {
          status.textContent = 'NEXO activo · sistema observado';
        }
      }

      renderHallazgos(data);
      actualizarConexion('PostgreSQL', data.integraciones?.postgresql);
      actualizarConexion('Ollama', data.integraciones?.ia_local);
      actualizarConexion('GitHub', data.integraciones?.github);
      renderV2(data.nexo_v2 || {});
    } catch (err) {
      if (status) status.textContent = err?.name === 'AbortError'
        ? 'NEXO excedió el tiempo de análisis'
        : 'NEXO no pudo consultar el endpoint de estado';
      const list = $('[data-findings]');
      if (list) list.innerHTML = `
        <div class="finding alta">
          <b>No fue posible consultar NEXO</b>
          <p>${err?.name === 'AbortError'
            ? 'La consulta superó 20 segundos. Revise carga del servidor y PostgreSQL.'
            : 'El endpoint no respondió correctamente. Revise la aplicación, PostgreSQL y la bitácora del servidor.'}</p>
        </div>`;
      console.error('SICODE NEXO:', err);
    } finally {
      window.clearTimeout(timeout);
      if (btn) btn.disabled = false;
    }
  }


  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const estados = [
    ['nueva', 'Nueva'], ['en_revision', 'En revisión'],
    ['aprobada', 'Aprobada'], ['descartada', 'Descartada'],
    ['implementada', 'Implementada'],
  ];

  async function postJSON(url, datos) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf},
      credentials: 'same-origin',
      body: JSON.stringify(datos),
    });
    let data;
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) throw new Error(data.error || 'Error HTTP ' + response.status);
    return data;
  }

  function renderV2(data) {
    const counts = data.indicadores || {};
    const labels = [
      ['expedientes_sin_fisico', 'SP sin expediente físico'],
      ['expedientes_sin_rectificacion', 'Rectificaciones pendientes'],
      ['documentos_rango_invalido', 'Rangos documentales inconsistentes'],
      ['prestamos_vencidos', 'Préstamos vencidos'],
      ['alertas_abiertas', 'Alertas abiertas'],
    ];
    const indicadores = $('[data-indicators]');
    if (indicadores) {
      indicadores.replaceChildren();
      for (const [clave, titulo] of labels) {
        const tarjeta = document.createElement('div');
        const numero = document.createElement('strong');
        numero.textContent = String(counts[clave] ?? '—');
        const texto = document.createElement('span');
        texto.textContent = titulo;
        tarjeta.append(numero, texto);
        indicadores.append(tarjeta);
      }
    }
    const memoria = data.memoria || {};
    const summary = $('[data-proposals-summary]');
    if (summary) summary.textContent = (memoria.total ?? 0)
      + ' propuestas registradas · ' + (memoria.por_estado?.nueva ?? 0)
      + ' nuevas · ' + (memoria.por_estado?.aprobada ?? 0) + ' aprobadas.';
    const ultima = $('[data-last-review]');
    if (ultima) ultima.textContent = data.ultima_revision
      ? 'Última revisión programada/manual: ' + new Date(data.ultima_revision).toLocaleString('es-GT')
      : 'Todavía no hay una revisión programada registrada.';
    const actividad = data.actividad || {};
    const linea = $('[data-nexo-activity]');
    if (linea) linea.textContent = 'Últimos 7 días: ' + (actividad.revisiones ?? 0)
      + ' revisiones · ' + (actividad.aprendizajes ?? 0) + ' aprendizajes · '
      + (actividad.propuestas_nuevas ?? 0) + ' propuestas nuevas.';
    const lista = $('[data-proposals-list]');
    if (!lista) return;
    lista.replaceChildren();
    const propuestas = memoria.propuestas || [];
    if (!propuestas.length) {
      const vacio = document.createElement('p');
      vacio.textContent = 'Sin propuestas registradas. Ejecute una revisión para analizar indicadores.';
      lista.append(vacio);
    }
    for (const propuesta of propuestas) {
      const articulo = document.createElement('article');
      articulo.className = 'nexo-proposal';
      const titulo = document.createElement('h3');
      titulo.textContent = propuesta.titulo || 'Propuesta';
      const meta = document.createElement('small');
      meta.textContent = (propuesta.modulo || 'SICODE') + ' · Prioridad '
        + (propuesta.prioridad || 'media') + ' · Revisiones con cambios: '
        + (propuesta.apariciones || 1);
      const detalle = document.createElement('p');
      detalle.textContent = propuesta.detalle || '';
      const accion = document.createElement('p');
      accion.textContent = 'Sugerencia: ' + (propuesta.recomendacion || '');
      const pie = document.createElement('div');
      pie.className = 'nexo-proposal-actions';
      const selector = document.createElement('select');
      selector.setAttribute('aria-label', 'Estado de ' + propuesta.titulo);
      for (const [value, label] of estados) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        selector.append(option);
      }
      selector.value = propuesta.estado || 'nueva';
      const guardar = document.createElement('button');
      guardar.type = 'button';
      guardar.className = 'nexo-refresh';
      guardar.textContent = 'Guardar decisión';
      guardar.disabled = true;
      selector.addEventListener('change', () => {
        guardar.disabled = selector.value === propuesta.estado;
      });
      guardar.addEventListener('click', async () => {
        guardar.disabled = true;
        try {
          await postJSON('/nexo/propuestas/' + propuesta.id + '/estado', {estado: selector.value});
          await cargar();
        } catch (error) {
          alert(error.message || 'No fue posible guardar la decisión');
          guardar.disabled = false;
        }
      });
      pie.append(selector, guardar);
      articulo.append(titulo, meta, detalle, accion, pie);
      lista.append(articulo);
    }
  }

  function agregarMensaje(texto, tipo) {
    const historial = $('[data-chat-history]');
    if (!historial) return;
    const mensaje = document.createElement('div');
    mensaje.className = 'nexo-chat-message ' + (tipo === 'user' ? 'nexo-chat-user' : 'nexo-chat-bot');
    mensaje.textContent = String(texto || '');
    historial.append(mensaje);
    // Memoria de chat sólo en la página; no se transmite historial al servidor.
    while (historial.children.length > 12) historial.firstElementChild?.remove();
    historial.scrollTop = historial.scrollHeight;
  }

  $('[data-chat-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = $('[data-chat-input]');
    const boton = $('[data-chat-send]');
    const status = $('[data-chat-status]');
    const pregunta = input?.value?.trim() || '';
    if (pregunta.length < 3 || pregunta.length > 600) return;
    boton.disabled = true;
    agregarMensaje(pregunta, 'user');
    input.value = '';
    status.textContent = 'Consultando al asistente local…';
    try {
      const r = await postJSON('/nexo/chat', {pregunta});
      agregarMensaje(r.respuesta, 'bot');
      status.textContent = r.modo === 'ollama'
        ? 'Respuesta de Ollama basada en indicadores agregados; verifique sus conclusiones.'
        : 'Ollama no disponible: resumen calculado con reglas verificables.';
    } catch (error) {
      agregarMensaje('No fue posible completar la consulta: ' + error.message, 'bot');
      status.textContent = 'Consulta fallida; revise la disponibilidad del servidor.';
    } finally {
      boton.disabled = false;
      input.focus();
    }
  });

  $('[data-revision]')?.addEventListener('click', async () => {
    const boton = $('[data-revision]');
    boton.disabled = true;
    boton.textContent = 'Revisando…';
    try {
      const r = await postJSON('/nexo/revision', {});
      boton.textContent = 'Revisión terminada';
      await cargar();
      const summary = $('[data-proposals-summary]');
      if (summary) summary.textContent += ' Nuevas en esta revisión: '
        + (r.revision?.propuestas_nuevas ?? 0) + '.';
    } catch (error) {
      boton.textContent = 'Reintentar revisión';
      alert('NEXO no pudo completar la revisión: ' + error.message);
    } finally {
      boton.disabled = false;
    }
  });

  $('[data-refresh]')?.addEventListener('click', cargar);
  cargar();
})();
