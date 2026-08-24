(() => {
  const reloj = document.querySelector('[data-reloj-guatemala]');
  if (!reloj) return;

  const formatterHora = new Intl.DateTimeFormat('es-GT', {
    timeZone: 'America/Guatemala',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const formatterFecha = new Intl.DateTimeFormat('es-GT', {
    timeZone: 'America/Guatemala',
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });

  function actualizarReloj() {
    const ahora = new Date();
    reloj.textContent = formatterHora.format(ahora);
    reloj.setAttribute('datetime', ahora.toISOString());
    reloj.title = `Hora de Guatemala · ${formatterFecha.format(ahora)}`;
  }

  actualizarReloj();

  // Alinea las actualizaciones al cambio real de segundo para que el reloj no
  // quede visualmente desplazado por el momento exacto en que cargó la página.
  const esperaInicial = 1000 - (Date.now() % 1000);
  window.setTimeout(() => {
    actualizarReloj();
    window.setInterval(actualizarReloj, 1000);
  }, esperaInicial);
})();
