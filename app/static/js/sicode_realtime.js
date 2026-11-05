/* SICODE-UCT: sincronización entre navegadores sin recargar la página completa.
 * SSE/Redis transmite únicamente invalidaciones. Nunca datos de expedientes.
 */
(() => {
  "use strict";
  if (!document.body.dataset.sicodeUser || !window.EventSource) return;

  const estado = document.createElement("span");
  estado.id = "sicode-sincronizacion-estado";
  estado.className = "sicode-sincronizacion-estado desconectado";
  estado.setAttribute("role", "status");
  estado.setAttribute("aria-live", "polite");
  estado.textContent = "Sincronización: conectando…";
  document.querySelector(".topbar-utilidad")?.append(estado);

  function marcar(conectado) {
    estado.classList.toggle("desconectado", !conectado);
    estado.textContent = conectado ? "● En tiempo real" : "○ Reconectando…";
    estado.title = conectado
      ? "Cambios sincronizados entre sesiones autorizadas"
      : "Sin conexión al canal de actualizaciones. Los datos se resincronizarán al reconectar.";
  }

  const omitir = "SCRIPT,STYLE,FORM,DIALOG,INPUT,TEXTAREA,SELECT,IFRAME,CANVAS,VIDEO";
  const clave = n => {
    if (n.nodeType !== 1) return "";
    if (n.id) return "id:" + n.id;
    for (const key of ["syncKey", "actividad", "registroId", "expedienteId"]) {
      if (n.dataset[key]) return key + ":" + n.dataset[key];
    }
    return "";
  };
  const protegido = n => n.nodeType === 1 && (
    n.matches(omitir + ',[data-sicode-no-sync],[contenteditable="true"]') ||
    n === document.activeElement
  );

  // Reconciliación conservadora: conserva nodos existentes, eventos asociados,
  // inputs, formularios y diálogos. No reemplaza <main> ni navega fuera de la vista.
  function reconciliar(actual, nuevo) {
    if (actual.nodeType !== nuevo.nodeType ||
        (actual.nodeType === 1 && actual.tagName !== nuevo.tagName)) {
      const reemplazo = nuevo.cloneNode(true);
      actual.replaceWith(reemplazo);
      return reemplazo;
    }
    if (actual.nodeType === 3) {
      if (actual.nodeValue !== nuevo.nodeValue) actual.nodeValue = nuevo.nodeValue;
      return actual;
    }
    if (actual.nodeType !== 1 || protegido(actual)) return actual;
    for (const attr of [...actual.attributes]) {
      if (!nuevo.hasAttribute(attr.name)) actual.removeAttribute(attr.name);
    }
    for (const attr of [...nuevo.attributes]) {
      if (actual.getAttribute(attr.name) !== attr.value) actual.setAttribute(attr.name, attr.value);
    }
    const nuevos = [...nuevo.childNodes];
    let cursor = actual.firstChild;
    for (const candidato of nuevos) {
      if (!cursor) {
        actual.appendChild(candidato.cloneNode(true));
        continue;
      }
      const identificador = clave(candidato);
      let coincidente = cursor;
      if (identificador && clave(cursor) !== identificador) {
        coincidente = [...actual.childNodes].find(n => clave(n) === identificador) || null;
      }
      if (!coincidente) {
        actual.insertBefore(candidato.cloneNode(true), cursor);
        continue;
      }
      if (coincidente !== cursor) actual.insertBefore(coincidente, cursor);
      coincidente = reconciliar(coincidente, candidato);
      cursor = coincidente.nextSibling;
    }
    while (cursor) {
      const siguiente = cursor.nextSibling;
      if (!protegido(cursor)) cursor.remove();
      cursor = siguiente;
    }
    return actual;
  }

  // Las vistas con su propio renderizador (Agenda UCT) se actualizan mediante
  // su API; el resto recibe actualización incremental del HTML autorizado.
  let pendiente = false, procesando = false, cola = false;
  async function refrescarVista() {
    if (document.querySelector("[data-agenda-root]")) return;
    if (document.hidden) { pendiente = true; return; }
    if (document.querySelector("dialog[open],[aria-modal='true']")) {
      pendiente = true;
      return;
    }
    if (procesando) { cola = true; return; }
    procesando = true;
    pendiente = false;
    try {
      const url = window.location.href;
      const respuesta = await fetch(url, {
        method: "GET", credentials: "same-origin", cache: "no-store",
        headers: { "Accept": "text/html", "X-SICODE-Revalidacion": "1" },
      });
      if (!respuesta.ok || respuesta.redirected ||
          !respuesta.headers.get("content-type")?.includes("text/html") ||
          window.location.href !== url) return;
      const documento = new DOMParser().parseFromString(await respuesta.text(), "text/html");
      const actual = document.querySelector("main.contenedor");
      const nuevo = documento.querySelector("main.contenedor");
      if (!actual || !nuevo) return;
      const y = window.scrollY, x = window.scrollX;
      reconciliar(actual, nuevo);
      window.scrollTo(x, y);
    } catch (_) {
      pendiente = true;
    } finally {
      procesando = false;
      if (cola) { cola = false; solicitarRefresco(); }
    }
  }
  let programado = false;
  function solicitarRefresco() {
    if (programado) return;
    programado = true;
    setTimeout(() => { programado = false; refrescarVista(); }, 160);
  }

  let conectoAntes = false, ultimoEvento = "";
  const fuente = new EventSource("/sincronizacion/eventos", {withCredentials: true});
  fuente.addEventListener("listo", () => {
    marcar(true);
    if (conectoAntes) {
      window.dispatchEvent(new CustomEvent("sicode:reconexion"));
      solicitarRefresco();
    }
    conectoAntes = true;
  });
  fuente.addEventListener("cambio", e => {
    if (e.lastEventId && ultimoEvento === e.lastEventId) return;
    if (e.lastEventId) ultimoEvento = e.lastEventId;
    try {
      const datos = JSON.parse(e.data);
      if (!Array.isArray(datos.modulos)) return;
      window.dispatchEvent(new CustomEvent("sicode:actualizacion", {detail: datos}));
      solicitarRefresco();
    } catch (_) { /* El mensaje inválido no debe interrumpir la sesión. */ }
  });
  fuente.onerror = () => marcar(false);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && pendiente) solicitarRefresco();
  });
  // Si había un modal abierto, actualizamos al volver a la vista ordinaria.
  document.addEventListener("close", () => {
    if (pendiente) solicitarRefresco();
  }, true);
  window.addEventListener("pagehide", () => fuente.close());
})();
