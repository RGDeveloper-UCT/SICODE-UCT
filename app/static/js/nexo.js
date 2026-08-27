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

  $('[data-refresh]')?.addEventListener('click', cargar);
  cargar();
})();
