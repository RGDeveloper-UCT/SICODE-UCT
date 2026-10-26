(() => {
  "use strict";
  const root = document.querySelector("[data-agenda-root]");
  if (!root) return;
  const editable = root.dataset.puedeModificar === "1";
  const currentId = Number(root.dataset.user);
  let items = [], cumpleanos = [], avisos = [];
  let fechaCalendario = new Date();
  let vista = "mes", actual = null;
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
  const safe = val => String(val ?? "").replace(/[&<>"']/g, x => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[x]));
  // Nunca insertar URL ni texto de usuario sin escaparlo. Solo http(s) es clicable.
  function conEnlaces(valor) {
    const texto = String(valor ?? "");
    const patron = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi;
    let salida = "", posicion = 0;
    for (const hallazgo of texto.matchAll(patron)) {
      const inicio = hallazgo.index;
      const visible = hallazgo[0].replace(/[.,;:!?)}\]]+$/, "");
      salida += safe(texto.slice(posicion, inicio));
      const destinoTexto = /^www\./i.test(visible) ? "https://" + visible : visible;
      try {
        const destino = new URL(destinoTexto);
        if (["http:", "https:"].includes(destino.protocol) && destino.hostname) {
          salida += '<a href="' + safe(destino.href) +
            '" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">' +
            safe(visible) + "</a>";
        } else {
          salida += safe(visible);
        }
      } catch (_) {
        salida += safe(visible);
      }
      posicion = inicio + visible.length;
    }
    return salida + safe(texto.slice(posicion));
  }
  const campoDetalle = (titulo, contenido) =>
    '<div class="agenda-detalle-dato"><dt>' + safe(titulo) + '</dt><dd>' + contenido + '</dd></div>';
  const fechaInicio = x => (x.inicio || x.vencimiento || "").slice(0, 10);
  const fechaFin = x => (x.vencimiento || x.inicio || "").slice(0, 10);
  const ocupaDia = (x, dia) => Boolean(fechaInicio(x) && fechaInicio(x) <= dia && fechaFin(x) >= dia);

  const dias = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
  const meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  const p = (num) => String(num).padStart(2, "0");
  const localIso = d => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  const hoy = () => localIso(new Date());
  const fecha = (iso, todoElDia=false) => iso ? new Date(iso).toLocaleString("es-GT", todoElDia ? {dateStyle:"medium"} : {dateStyle:"medium", timeStyle:"short"}) : "Sin fecha";
  const datetimeInput = val => val ? val.substring(0, 16) : "";
  const notification = msg => {
    let e = $("#agenda-toast");
    if (!e) { e = document.createElement("div"); e.id = "agenda-toast"; e.setAttribute("role","status"); document.body.append(e); }
    e.textContent = msg;
    e.classList.add("activo");
    setTimeout(() => e.classList.remove("activo"), 4200);
  };
  async function api(path, options = {}) {
    const token = $('meta[name="csrf-token"]')?.content || "";
    const respuesta = await fetch("/agenda" + path, {
      credentials: "same-origin", ...options,
      headers: {"Accept":"application/json", ...(options.body ? {"Content-Type":"application/json", "X-CSRFToken":token} : {}), ...(options.headers || {})},
    });
    let datos;
    try { datos = await respuesta.json(); } catch (_) { throw new Error("Error inesperado del servidor."); }
    if (!respuesta.ok) throw new Error(datos.error || `Error HTTP ${respuesta.status}`);
    return datos;
  }
  const post = (url, data) => api(url, {method:"POST", body:JSON.stringify(data)});
  const miActividad = x => x.creado_por_id === currentId || x.responsable_id === currentId || x.participantes.includes(currentId);
  const tituloTipo = {tarea:"Tarea", evento:"Evento", capacitacion:"Capacitación", gestion:"Gestión", mantenimiento:"Mantenimiento"};
  function tarjeta(x, completa = false) {
    const marca = x.estado === "finalizada" ? "✓" : "○";
    return `<article class="agenda-tarjeta agenda-p-${safe(x.prioridad)}" data-actividad="${x.id}" tabindex="0" draggable="${editable ? "true" : "false"}" role="button" aria-label="Ver actividad ${safe(x.titulo)}">
      <div class="agenda-tarjeta-arriba"><span class="agenda-marca">${marca}</span><strong>${safe(x.titulo)}</strong></div>
      <small class="agenda-etiqueta">${safe(tituloTipo[x.tipo] || x.tipo)}</small>
      <div class="agenda-tarjeta-info"><span>◷ ${safe(fecha(x.vencimiento))}</span><span>♙ ${safe(x.responsable)}</span></div>
      <div class="agenda-progreso"><span style="width:${x.progreso}%"></span></div>
      ${x.referencia_sp ? `<small>SP: ${safe(x.referencia_sp)}</small>` : ""}
    </article>`;
  }
  function abrirTab(tab) {
    $$("[data-agenda-tab]", root).forEach(b => { const activo = b.dataset.agendaTab === tab; b.classList.toggle("activo", activo); b.setAttribute("aria-selected", String(activo)); });
    $$("[data-agenda-panel]", root).forEach(el => el.hidden = el.dataset.agendaPanel !== tab);
    if (location.hash !== "#" + tab) history.replaceState(null, "", "#" + tab);
  }
  function cargarKpis() {
    const hoyFecha = hoy(), limite = new Date(); limite.setDate(limite.getDate() + 3);
    const mis = items.filter(miActividad);
    const cuenta = {
      pendientes:mis.filter(x=> x.estado === "pendiente").length,
      proceso:mis.filter(x=> x.estado === "en_proceso").length,
      eventos:mis.filter(x=> x.tipo !== "tarea" && !x.padre_id && fechaFin(x) >= hoyFecha && !["cancelada","finalizada"].includes(x.estado)).length,
      vencimientos:mis.filter(x=> x.vencimiento && x.vencimiento.slice(0,10) <= localIso(limite) && x.estado !== "finalizada" && x.estado !== "cancelada").length,
      finalizadas:mis.filter(x=> x.estado === "finalizada").length
    };
    Object.entries(cuenta).forEach(([key, val]) => {const el = $('[data-kpi="' + key + '"]'); if(el) el.textContent = val;});
  }
  function pintarTablero() {
    const q = ($("#agenda-buscar")?.value || "").toLocaleLowerCase();
    const tipo = $("#agenda-filtro-tipo")?.value || "";
    const mias = $("#agenda-solo-mias")?.checked;
    const validos = items.filter(x => (!q || x.titulo.toLowerCase().includes(q)) && (!tipo || x.tipo === tipo) && (!mias || miActividad(x)));
    $$("[data-agenda-estado]", root).forEach(col=>{
      const registros = validos.filter(x=>x.estado === col.dataset.agendaEstado && !x.padre_id);
      col.innerHTML = registros.map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">Sin actividades.</p>';
      col.closest(".agenda-kanban-col").querySelector("h2").dataset.cuenta = registros.length;
    });
    $("#agenda-otros").innerHTML = validos.filter(x=>["bloqueada","cancelada"].includes(x.estado)).map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">Sin actividades bloqueadas o canceladas.</p>';
  }
  function pintarListas() {
    const fechaHoy = hoy();
    const actividadesDia = items.filter(x=> miActividad(x) && x.estado !== "finalizada" && x.estado !== "cancelada" &&
      (x.vencimiento && x.vencimiento.slice(0,10) <= fechaHoy || x.inicio && x.inicio.slice(0,10) === fechaHoy));
    $("#agenda-hoy").innerHTML = actividadesDia.map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">Sin actividades urgentes para hoy.</p>';
    $("#agenda-tareas").innerHTML = items.filter(x=> x.tipo === "tarea").map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">No hay tareas registradas.</p>';
    $("#agenda-eventos").innerHTML = items.filter(x=> x.tipo !== "tarea" && !x.padre_id).map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">No hay eventos registrados.</p>';
  }
  const distanciaCumple = c => {
    const d = new Date(), actual = new Date(d.getFullYear(), c.mes-1, c.dia);
    if (actual < new Date(d.getFullYear(), d.getMonth(), d.getDate())) actual.setFullYear(actual.getFullYear()+1);
    return Math.ceil((actual - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  };
  function pintarCumpleanos() {
    const orden = [...cumpleanos].sort((a,b)=>distanciaCumple(a)-distanciaCumple(b));
    const html = orden.map(c => `<div class="agenda-cumple-linea"><span>♧</span><strong>${safe(c.nombre)}</strong><small>${c.dia} de ${meses[c.mes-1]} · en ${distanciaCumple(c)} días</small></div>`).join("");
    $("#agenda-cumpleanos-lista").innerHTML = html || '<p class="agenda-vacio">No hay cumpleaños compartidos.</p>';
    $("#agenda-proximos-cumple").innerHTML = orden.slice(0,5).map(c=>`<p>♧ ${safe(c.nombre)} — ${c.dia}/${c.mes}</p>`).join("") || '<p class="agenda-vacio">Sin fechas compartidas.</p>';
  }
  function pintarAvisos() {
    $("#agenda-avisos-lista").innerHTML = avisos.map(x=>`<div class="agenda-aviso agenda-p-${safe(x.prioridad)}">
      <div><strong>${safe(x.titulo)}</strong><p>${safe(x.mensaje)}</p></div>
      <div class="agenda-acciones"><button class="agenda-boton" type="button" data-agenda-aviso="${x.id}">${x.obligatoria ? "Confirmar enterado" : "Marcar leído"}</button>
      ${x.actividad_id ? `<button class="agenda-boton" type="button" data-agenda-detalle="${x.actividad_id}">Ver tarea</button>` : ""}</div>
    </div>`).join("") || '<p class="agenda-vacio">Sin notificaciones pendientes.</p>';
  }
  function pintarCalendario() {
    const cont = $("#agenda-calendario");
    const y = fechaCalendario.getFullYear(), m = fechaCalendario.getMonth();
    $("#agenda-calendario-titulo").textContent = `${meses[m]} ${y}`;
    const porDia = fechaISO => items.filter(x => ocupaDia(x, fechaISO));
    const celda = d => {
      const k = localIso(d), seleccion = k === hoy() ? " agenda-hoy-dia" : "";
      const lista = porDia(k).slice(0,4).map(x=>`<button type="button" class="agenda-cal-item agenda-p-${safe(x.prioridad)}" data-agenda-detalle="${x.id}" title="${safe(x.titulo)}">${safe(x.titulo)}</button>`).join("");
      return `<div class="agenda-cal-dia${seleccion}"><button type="button" class="agenda-num-dia" data-agenda-fecha="${k}">${d.getDate()}</button>${lista}</div>`;
    };
    if (vista === "agenda") {
      cont.className = "agenda-calendario agenda-cal-lista";
      const inicioMes = localIso(new Date(y, m, 1));
      const finMes = localIso(new Date(y, m + 1, 0));
      cont.innerHTML = items.filter(x => fechaInicio(x) && fechaInicio(x) <= finMes && fechaFin(x) >= inicioMes)
        .sort((a,b) => fechaInicio(a).localeCompare(fechaInicio(b)))
        .map(x => tarjeta(x)).join("") || '<p class="agenda-vacio">Sin actividades para este mes.</p>';
      return;
    }
    if (vista === "dia") {
      cont.className = "agenda-calendario agenda-cal-lista";
      cont.innerHTML = `<h3>${safe(localIso(fechaCalendario))}</h3>` + (porDia(localIso(fechaCalendario)).map(x=>tarjeta(x)).join("") || '<p class="agenda-vacio">Sin eventos.</p>');
      return;
    }
    let fechas=[];
    if (vista === "mes") {
      const inicio = new Date(y,m,1), primero = new Date(y,m,1-inicio.getDay());
      for(let i=0;i<42;i++) fechas.push(new Date(primero.getFullYear(), primero.getMonth(), primero.getDate()+i));
    } else {
      const inicio = new Date(y,m,fechaCalendario.getDate());
      const primer = inicio.getDate() - (vista === "laboral" ? (inicio.getDay()+6)%7 : inicio.getDay());
      for(let i=0;i<(vista === "laboral" ? 5:7);i++) fechas.push(new Date(y,m,primer+i));
    }
    cont.className = "agenda-calendario agenda-cal-grid";
    const nombres = vista === "laboral" ? ["Lun","Mar","Mié","Jue","Vie"] : dias;
    cont.innerHTML = nombres.map(d=>`<strong class="agenda-cal-dia-semana">${d}</strong>`).join("") + fechas.map(celda).join("");
    cont.style.gridTemplateColumns = `repeat(${nombres.length}, minmax(0,1fr))`;
  }
  async function refrescar() {
    try {
      const [a,b,c]=await Promise.all([api("/api/actividades"), api("/api/cumpleanos"), api("/api/avisos")]);
      items=a.actividades; cumpleanos=b.cumpleanos; avisos=c.avisos;
      cargarKpis(); pintarTablero(); pintarListas(); pintarCalendario(); pintarCumpleanos(); pintarAvisos();
    } catch(error) { notification(error.message); }
  }
  function formulario(actividad=null, fechaElegida=null, padre=null, tipo="tarea") {
    const dlg=$("#agenda-form-dialog"); if(!dlg) return;
    const form=$("#agenda-actividad-form"); form.reset();
    form.elements.actividad_id.value = actividad?.id ?? "";
    form.elements.padre_id.value = padre ?? "";
    form.elements.titulo.value = actividad?.titulo ?? "";
    form.elements.descripcion.value = actividad?.descripcion ?? "";
    form.elements.tipo.value = actividad?.tipo ?? tipo;
    form.elements.prioridad.value = actividad?.prioridad ?? "media";
    form.elements.responsable_id.value = actividad?.responsable_id ?? currentId;
    form.elements.inicio.value = datetimeInput(actividad?.inicio) || (fechaElegida ? fechaElegida+"T09:00" : "");
    form.elements.vencimiento.value = datetimeInput(actividad?.vencimiento) || (fechaElegida ? fechaElegida+"T10:00" : "");
    form.elements.recurrencia.value = actividad?.recurrencia ?? "ninguna";
    form.elements.visibilidad.value = actividad?.visibilidad ?? "equipo";
    form.elements.lugar.value = actividad?.lugar ?? "";
    form.elements.modalidad.value = actividad?.modalidad ?? "";
    form.elements.referencia_sp.value = actividad?.referencia_sp ?? "";
    form.elements.requiere_revision.checked = Boolean(actividad?.requiere_revision);
    form.elements.todo_el_dia.checked = Boolean(actividad?.todo_el_dia);
    $$('input[name="participantes"]',form).forEach(c=>c.checked = Boolean(actividad?.participantes?.includes(Number(c.value))));
    $("#agenda-form-titulo").textContent = actividad ? "Editar actividad" : padre ? "Nueva subtarea" : "Nueva actividad";
    dlg.showModal();
    form.elements.titulo.focus();
  }
  function textoEstado(s){ return ({pendiente:"Pendiente",en_proceso:"En proceso",en_revision:"En revisión",finalizada:"Finalizada",bloqueada:"Bloqueada",cancelada:"Cancelada"})[s]||s; }
  async function detalle(id) {
    try {
      const data = await api("/api/actividades/"+id);
      actual = data.actividad;
      const x=actual, notas=data.comentarios, subtareas=data.subtareas;
      const puede = editable && miActividad(x);
      $("#agenda-detalle-titulo").textContent=x.titulo;
      $("#agenda-detalle-contenido").innerHTML = `
        <h3>Descripción</h3>
        <div class="agenda-texto-enlaces">${x.descripcion ? conEnlaces(x.descripcion) : "Sin descripción."}</div>
        <dl class="agenda-detalle-datos">
          ${campoDetalle("Tipo", safe(tituloTipo[x.tipo] || x.tipo))}
          ${campoDetalle("Prioridad", safe(x.prioridad))}
          ${campoDetalle("Estado", safe(textoEstado(x.estado)))}
          ${campoDetalle("Responsable", safe(x.responsable))}
          ${campoDetalle("Inicio", safe(fecha(x.inicio, x.todo_el_dia)))}
          ${campoDetalle("Vencimiento / final", safe(fecha(x.vencimiento, x.todo_el_dia)))}
          ${campoDetalle("Creador", safe(x.creado_por))}
          ${campoDetalle("SP", safe(x.referencia_sp || "No aplica"))}
          ${campoDetalle("Repetición", safe(x.recurrencia))}
          ${campoDetalle("Visibilidad", x.visibilidad === "personal" ? "Privada / participantes" : "Institucional / equipo")}
          ${campoDetalle("Lugar / enlace", x.lugar ? conEnlaces(x.lugar) : "No especificado")}
          ${campoDetalle("Modalidad", safe(({presencial:"Presencial",virtual:"Virtual",mixta:"Mixta"})[x.modalidad] || x.modalidad || "Sin definir"))}
          ${campoDetalle("Requiere revisión del creador", x.requiere_revision ? "Sí" : "No")}
          ${campoDetalle("Todo el día", x.todo_el_dia ? "Sí" : "No")}
          ${campoDetalle("Progreso", safe(x.progreso) + "%")}
          ${x.padre_id ? campoDetalle("Actividad principal", "#" + safe(x.padre_id)) : ""}
        </dl>
        ${puede ? `<div class="agenda-acciones"><button type="button" class="agenda-boton" data-agenda-editar>Editar</button>
        <select id="agenda-estado-nuevo" aria-label="Estado">${["pendiente","en_proceso","en_revision","finalizada","bloqueada","cancelada"].map(e=>`<option value="${e}" ${e===x.estado?"selected":""}>${textoEstado(e)}</option>`).join("")}</select>
        <button type="button" class="agenda-boton agenda-primario" data-agenda-guardar-estado>Cambiar estado</button></div>` : ""}
        <h3>Subtareas (${subtareas.length})</h3><div class="agenda-lista">${subtareas.map(s=>`<button type="button" class="agenda-subtarea" data-agenda-detalle="${s.id}">☑ ${safe(s.titulo)} — ${safe(textoEstado(s.estado))}</button>`).join("") || "<p>Sin subtareas.</p>"}</div>
        ${puede && !x.padre_id ? '<button type="button" class="agenda-boton" data-agenda-subtarea>＋ Añadir subtarea</button>':""}
        ${x.tipo === "tarea" ? `<h3>Participantes / colaboradores</h3><div class="agenda-lista">${data.asistencias.map(a=>`<p>${safe(a.nombre)}</p>`).join("") || "<p>Sin colaboradores adicionales.</p>"}</div>` : ""}
        ${x.tipo !== "tarea" && !data.asistencias.length ? "<h3>Confirmaciones de asistencia</h3><p>Sin participantes registrados.</p>" : ""}
        ${x.tipo !== "tarea" && data.asistencias.length ? `<h3>Confirmaciones de asistencia</h3><div>${data.asistencias.map(a=>`<p>${safe(a.nombre)} — ${safe(a.respuesta)}</p>`).join("")}</div>
        ${data.asistencias.some(a=>a.usuario_id===currentId)?'<div class="agenda-acciones"><button type="button" class="agenda-boton" data-agenda-rsvp="aceptada">Asistiré</button><button type="button" class="agenda-boton" data-agenda-rsvp="rechazada">No asistiré</button></div>':""}` : ""}
        <h3>Comentarios</h3><div class="agenda-lista">${notas.map(n=>`<p class="agenda-texto-enlaces"><strong>${safe(n.usuario)}:</strong> ${conEnlaces(n.texto)} <small>${safe(fecha(n.fecha))}</small></p>`).join("") || '<p>Sin comentarios todavía.</p>'}</div>
        ${puede ? '<form id="agenda-form-comentario"><textarea name="texto" maxlength="2000" placeholder="Escriba una actualización…" required></textarea><button type="submit" class="agenda-boton">Agregar comentario</button></form>' : ""}`;
      $("#agenda-detalle-dialog").showModal();
    } catch(error) { notification(error.message); }
  }
  document.addEventListener("click", async e => {
    const btnTab = e.target.closest("[data-agenda-tab]");
    if(btnTab && root.contains(btnTab)) { abrirTab(btnTab.dataset.agendaTab); return; }
    const nuevo = e.target.closest("[data-agenda-crear]");
    if (nuevo) { formulario(null,null,null,nuevo.dataset.agendaTipo || "tarea"); return; }
    if (e.target.closest("[data-agenda-cerrar]")) { e.target.closest("dialog")?.close(); return; }
    const editar=e.target.closest("[data-agenda-editar]");
    if(editar && actual) { $("#agenda-detalle-dialog").close(); formulario(actual); return; }
    if(e.target.closest("[data-agenda-subtarea]") && actual) { $("#agenda-detalle-dialog").close(); formulario(null,null,actual.id); return; }
    if(e.target.closest("[data-agenda-guardar-estado]") && actual) {
      try { await post(`/api/actividades/${actual.id}/estado`,{estado:$("#agenda-estado-nuevo").value}); $("#agenda-detalle-dialog").close(); await refrescar(); notification("Estado actualizado."); } catch(err){notification(err.message);} return;
    }
    const asistencia=e.target.closest("[data-agenda-rsvp]");
    if(asistencia && actual) {try{await post(`/api/actividades/${actual.id}/asistencia`,{respuesta:asistencia.dataset.agendaRsvp});notification("Asistencia registrada.");await detalle(actual.id);}catch(err){notification(err.message);}return;}
    const aviso=e.target.closest("[data-agenda-aviso]");
    if(aviso) {try{const x=avisos.find(a=>a.id===Number(aviso.dataset.agendaAviso)); await post(`/api/avisos/${aviso.dataset.agendaAviso}/${x?.obligatoria?"confirmar":"leer"}`,{});await refrescar();notification("Notificación atendida.");}catch(err){notification(err.message);} return;}
    const fechaBtn=e.target.closest("[data-agenda-fecha]");
    if(fechaBtn) {if(editable) formulario(null,fechaBtn.dataset.agendaFecha,null,"evento");return;}
    const ver=e.target.closest("[data-agenda-detalle], [data-actividad]");
    if(ver) {await detalle(Number(ver.dataset.agendaDetalle || ver.dataset.actividad));return;}
    if (e.target.closest("#agenda-mes-anterior")) {fechaCalendario.setMonth(fechaCalendario.getMonth() - 1);pintarCalendario();}
    if (e.target.closest("#agenda-mes-siguiente")) {fechaCalendario.setMonth(fechaCalendario.getMonth() + 1);pintarCalendario();}
    if (e.target.closest("#agenda-ir-hoy")) {fechaCalendario=new Date();pintarCalendario();}
  });
  $("#agenda-actividad-form")?.addEventListener("submit", async e=>{
    e.preventDefault(); const f=e.currentTarget, data=Object.fromEntries(new FormData(f));
    data.participantes=$$('input[name="participantes"]:checked',f).map(el=>Number(el.value));
    data.requiere_revision=f.elements.requiere_revision.checked;
    data.todo_el_dia=f.elements.todo_el_dia.checked;
    const id=data.actividad_id; delete data.actividad_id;
    if (!data.padre_id) delete data.padre_id;
    try {
      if (id) await api("/api/actividades/"+id,{method:"PATCH",body:JSON.stringify(data)});
      else await post("/api/actividades",data);
      $("#agenda-form-dialog").close(); await refrescar(); notification("Actividad guardada.");
    }catch(err){notification(err.message);}
  });
  document.addEventListener("submit",async e=>{
    if(e.target.id==="agenda-form-comentario" && actual){
      e.preventDefault();
      try{await post(`/api/actividades/${actual.id}/comentarios`,{texto:e.target.elements.texto.value});await detalle(actual.id);notification("Comentario guardado.");}
      catch(err){notification(err.message);}
    }
  });
  $("#agenda-cumpleanos-form")?.addEventListener("submit", async e=>{
    e.preventDefault();
    const f=e.currentTarget;
    try{
      await post("/api/cumpleanos",{dia:Number(f.elements.dia.value),mes:Number(f.elements.mes.value),visible:f.elements.visible.checked});
      await refrescar();notification("Cumpleaños guardado con sus preferencias.");
    }catch(err){notification(err.message);}
  });
  $("#agenda-buscar")?.addEventListener("input",pintarTablero);
  $("#agenda-filtro-tipo")?.addEventListener("change",pintarTablero);
  $("#agenda-solo-mias")?.addEventListener("change",pintarTablero);
  $("#agenda-vista-calendario")?.addEventListener("change", e=>{vista=e.target.value;pintarCalendario();});
  let arrastrada=null;
  $("#agenda-kanban").addEventListener("dragstart",e=>{
    const el=e.target.closest("[data-actividad]");
    if(el){arrastrada=Number(el.dataset.actividad);e.dataTransfer.effectAllowed="move";}
  });
  $("#agenda-kanban").addEventListener("dragover",e=>{
    if(e.target.closest("[data-agenda-estado]")) e.preventDefault();
  });
  $("#agenda-kanban").addEventListener("drop",async e=>{
    const col=e.target.closest("[data-agenda-estado]");
    if(!col||!arrastrada)return;
    e.preventDefault();
    const id=arrastrada;arrastrada=null;
    try{await post(`/api/actividades/${id}/estado`,{estado:col.dataset.agendaEstado});await refrescar();notification("Actividad movida.");}
    catch(err){notification(err.message);}
  });
  const initial = location.hash.replace("#","");
  abrirTab($$("[data-agenda-tab]",root).some(x=>x.dataset.agendaTab===initial)?initial:"hoy");
  refrescar();
})();
