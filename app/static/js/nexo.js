(() => {
  const root = document.querySelector('[data-nexo]');
  if (!root) return;

  const $ = (s) => root.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  async function cargar() {
    const status = $('[data-nexo-status]');
    const btn = $('[data-refresh]');
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Analizando SICODE…';

    try {
      const response = await fetch(root.dataset.url, {headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const aprendizaje = data.aprendizaje || {};
      const totales = data.totales || {};
      const hallazgos = data.hallazgos || [];

      $('[data-kpi-level]').textContent = `${aprendizaje.nivel || 0}%`;
      $('[data-kpi-samples]').textContent = aprendizaje.muestras || 0;
      $('[data-kpi-findings]').textContent = data.hallazgos_total || hallazgos.length || 0;
      $('[data-kpi-objects]').textContent = (totales.objetos_estudiados || 0).toLocaleString('es-GT');
      $('[data-meter]').style.width = `${Math.max(2, Math.min(100, aprendizaje.nivel || 0))}%`;

      if (status) {
        status.textContent = data.estado === 'requiere_revision'
          ? 'Análisis completo · hay hallazgos para revisar'
          : 'NEXO activo · sistema observado';
      }

      const list = $('[data-findings]');
      if (!hallazgos.length) {
        list.innerHTML = '<div class="finding baja"><b>Sin hallazgos prioritarios</b><p>NEXO no detectó patrones que requieran atención en este análisis.</p></div>';
      } else {
        list.innerHTML = hallazgos.map(h => `
          <article class="finding ${esc(h.prioridad || 'media')}">
            <b>${esc(h.titulo || 'Hallazgo')}</b>
            <p>${esc(h.detalle || '')}</p>
            ${h.recomendacion ? `<small><strong>Recomendación:</strong> ${esc(h.recomendacion)}</small>` : ''}
          </article>`).join('');
      }

      const ia = data.integraciones?.ia_local;
      if (ia) {
        const rows = [...root.querySelectorAll('.connections > div')];
        const ollama = rows.find(x => x.textContent.includes('Ollama'));
        if (ollama) {
          const dot = ollama.querySelector('.connection-dot');
          if (dot) dot.className = `connection-dot ${ia.disponible ? 'active' : ''}`;
          const small = ollama.querySelector('small');
          if (small) small.textContent = ia.disponible ? `IA local activa · ${ia.modelo}` : 'IA local no disponible en este momento';
        }
      }
    } catch (err) {
      if (status) status.textContent = 'NEXO no pudo completar el análisis';
      const list = $('[data-findings]');
      if (list) list.innerHTML = '<div class="finding alta"><b>No fue posible consultar NEXO</b><p>Verifique la aplicación, PostgreSQL y la bitácora del servidor.</p></div>';
      console.error('SICODE NEXO:', err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  $('[data-refresh]')?.addEventListener('click', cargar);
  cargar();
})();
