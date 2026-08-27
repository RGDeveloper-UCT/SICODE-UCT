(() => {
  const body = document.body;
  if (!body?.dataset?.sicodeUser) return;

  const userId = body.dataset.sicodeUser;
  const storageKey = `sicode_ticket_soporte_${userId}`;
  const bubble = document.querySelector('[data-ticket-soporte-burbuja]');
  const bubbleClock = document.querySelector('[data-ticket-soporte-burbuja-reloj]');
  const bubbleState = document.querySelector('[data-ticket-soporte-burbuja-estado]');
  const overlay = document.querySelector('[data-ticket-soporte-inicio]');
  const overlayTitle = document.querySelector('[data-ticket-soporte-inicio-titulo]');
  const overlayText = document.querySelector('[data-ticket-soporte-inicio-texto]');
  const overlayClock = document.querySelector('[data-ticket-soporte-inicio-reloj]');
  const newTicketPath = '/coordinacion/soporte-tecnico/nuevo';
  const dashboardPath = '/dashboard';

  function readTicket() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !data.startedAt || data.closed) return null;
      return data;
    } catch (_) {
      return null;
    }
  }

  function writeTicket(ticket) {
    localStorage.setItem(storageKey, JSON.stringify(ticket));
  }

  function clearTicket() {
    localStorage.removeItem(storageKey);
    if (bubble) bubble.hidden = true;
  }

  function formatDuration(milliseconds) {
    const total = Math.max(0, Math.floor(milliseconds / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
  }

  function elapsed(ticket) {
    return Date.now() - Number(ticket.startedAt || Date.now());
  }

  function updateClocks() {
    const ticket = readTicket();
    if (!ticket) {
      if (bubble) bubble.hidden = true;
      return;
    }
    const value = formatDuration(elapsed(ticket));
    if (bubble) {
      bubble.hidden = false;
      bubble.href = ticket.resumeUrl || newTicketPath;
      bubble.dataset.ticketActive = '1';
    }
    if (bubbleClock) bubbleClock.textContent = value;
    if (bubbleState) bubbleState.textContent = ticket.label || 'Tiempo de resolución';
    if (overlayClock) overlayClock.textContent = value;
  }

  function showOverlay(ticket, alreadyActive = false) {
    if (!overlay) return Promise.resolve();
    if (overlayTitle) overlayTitle.textContent = alreadyActive
      ? 'Ticket de soporte en curso'
      : 'Tiempo de resolución iniciado';
    if (overlayText) overlayText.textContent = alreadyActive
      ? 'Ya existe un ticket activo. El cronómetro continúa sin reiniciarse.'
      : 'El cronómetro comenzó a contar y seguirá activo mientras utiliza SICODE.';
    overlay.classList.add('ticket-soporte-inicio--visible');
    overlay.setAttribute('aria-hidden', 'false');
    updateClocks();
    return new Promise((resolve) => {
      window.setTimeout(() => {
        overlay.classList.remove('ticket-soporte-inicio--visible');
        overlay.setAttribute('aria-hidden', 'true');
        resolve();
      }, 1150);
    });
  }

  function startTicket() {
    let ticket = readTicket();
    const alreadyActive = Boolean(ticket);
    if (!ticket) {
      ticket = {
        startedAt: Date.now(),
        resumeUrl: newTicketPath,
        draft: {},
        label: 'Tiempo de resolución',
        pendingSubmitState: null,
      };
      writeTicket(ticket);
    }
    return { ticket, alreadyActive };
  }

  function isPlainLeftClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  document.addEventListener('click', async (event) => {
    const link = event.target.closest('a');
    if (!link || !isPlainLeftClick(event)) return;
    let url;
    try {
      url = new URL(link.href, window.location.href);
    } catch (_) {
      return;
    }
    if (url.origin !== window.location.origin || url.pathname !== newTicketPath) return;

    event.preventDefault();
    const { ticket, alreadyActive } = startTicket();
    await showOverlay(ticket, alreadyActive);
    window.location.href = ticket.resumeUrl || newTicketPath;
  });

  // Acceso directo a /nuevo: inicia el ticket aunque no se haya llegado desde un enlace.
  if (window.location.pathname === newTicketPath && !readTicket()) {
    const { ticket } = startTicket();
    showOverlay(ticket, false);
  }

  // Después de un POST correcto el backend redirige al detalle de la boleta.
  // Si quedó Pendiente conservamos la burbuja para continuar el ticket. Si el
  // técnico lo cerró (Resuelto, Parcial o Escalado), limpiamos el cronómetro y
  // regresamos automáticamente al Dashboard para continuar trabajando en SICODE.
  const detailMatch = window.location.pathname.match(/^\/coordinacion\/soporte-tecnico\/boletas\/(\d+)$/);
  if (detailMatch) {
    const ticket = readTicket();
    if (ticket?.pendingSubmitState) {
      if (ticket.pendingSubmitState === 'PENDIENTE') {
        ticket.resumeUrl = `/coordinacion/soporte-tecnico/boletas/${detailMatch[1]}/editar`;
        ticket.pendingSubmitState = null;
        ticket.draft = {};
        writeTicket(ticket);
      } else {
        clearTicket();
        window.location.replace(dashboardPath);
        return;
      }
    }
  }

  window.SICODETicketSoporte = {
    read: readTicket,
    write: writeTicket,
    clear: clearTicket,
    formatDuration,
    elapsed,
    storageKey,
  };

  updateClocks();
  window.setInterval(updateClocks, 1000);
})();
