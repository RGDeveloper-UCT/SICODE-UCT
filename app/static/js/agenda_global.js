/* Acceso universal Agenda UCT y avisos con confirmación verificable tras login. */
(() => {
  "use strict";
  const ruta="/agenda/api";
  const token=document.querySelector('meta[name="csrf-token"]')?.content || "";
  const escapeHtml=s=>String(s??"").replace(/[&<>"']/g,x=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));
  async function get(path) {
    const r=await fetch(ruta+path,{credentials:"same-origin",headers:{"Accept":"application/json"}});
    if(!r.ok)throw new Error("No fue posible consultar las notificaciones.");
    return r.json();
  }
  async function confirmar(id) {
    const r=await fetch(ruta+"/avisos/"+id+"/confirmar",{
      method:"POST",credentials:"same-origin",headers:{"X-CSRFToken":token,"Content-Type":"application/json"},body:"{}"
    });
    if(!r.ok)throw new Error("No fue posible confirmar la lectura.");
    return r.json();
  }
  function actualizaContador(total){
    const marca=document.querySelector("[data-agenda-contador]");
    if(!marca)return;
    marca.textContent=total>99?"99+":String(total);
    marca.hidden=total===0;
    marca.setAttribute("aria-label",total+" avisos pendientes");
  }
  async function refrescarContador(){
    try{const d=await get("/avisos");actualizaContador(d.total||0);}catch(_){}
  }
  function mostrarPendientes(alertas) {
    if(!alertas.length)return;
    if(document.querySelector(".agenda-recordatorios-fondo"))return;
    const cont=document.createElement("div");
    cont.className="agenda-recordatorios-fondo";
    cont.setAttribute("role","presentation");
    cont.innerHTML=`<section class="agenda-recordatorios-modal" role="dialog" aria-modal="true" aria-labelledby="agenda-alerta-titulo" tabindex="-1">
      <h2 id="agenda-alerta-titulo">♧ Recordatorios y alertas del día</h2>
      <p>Revise los avisos de prioridad alta y media. Debe confirmar que está enterado antes de continuar.</p>
      <div data-alertas-contenido></div>
      <p class="agenda-recordatorios-pie" role="status">Las confirmaciones quedan registradas en la bitácora institucional.</p>
    </section>`;
    const lista=cont.querySelector("[data-alertas-contenido]");
    function pintar(){
      lista.innerHTML=alertas.map(x=>`<article class="agenda-recordatorio ${x.prioridad==="alta"?"rojo":"amarillo"}" data-aviso="${x.id}">
        <small>${x.prioridad==="alta"?"● PRIORIDAD ALTA — ROJO":"● PRIORIDAD MEDIA — AMARILLO"}</small>
        <h3>${escapeHtml(x.titulo)}</h3><p>${escapeHtml(x.mensaje)}</p>
        <button type="button" data-confirmar-aviso="${x.id}">✓ Confirmar enterado</button>
        ${x.actividad_id?`<span class="agenda-recordatorio-referencia">Referencia de actividad: #${x.actividad_id}</span>`:""}
      </article>`).join("");
    }
    pintar();
    document.body.append(cont);
    document.body.style.overflow="hidden";
    const modal=cont.querySelector('[role="dialog"]');
    modal.focus();
    const bloqueo=e=>{
      if(e.key==="Escape"){e.preventDefault();e.stopPropagation();}
      if(e.key==="Tab"){
        const focos=[...cont.querySelectorAll('button:not([disabled]),a[href]')];
        if(!focos.length){e.preventDefault();return;}
        const primero=focos[0],ultimo=focos[focos.length-1];
        if(e.shiftKey&&document.activeElement===primero){e.preventDefault();ultimo.focus();}
        if(!e.shiftKey&&document.activeElement===ultimo){e.preventDefault();primero.focus();}
      }
    };
    cont.addEventListener("keydown",bloqueo);
    cont.addEventListener("click",async e=>{
      const boton=e.target.closest("[data-confirmar-aviso]");
      if(!boton)return;
      boton.disabled=true;
      try{
        await confirmar(Number(boton.dataset.confirmarAviso));
        alertas=alertas.filter(x=>x.id!==Number(boton.dataset.confirmarAviso));
        if(!alertas.length){
          cont.remove();document.body.style.overflow="";refrescarContador();
        }else{pintar();cont.querySelector("button")?.focus();}
      }catch(err){boton.disabled=false;cont.querySelector(".agenda-recordatorios-pie").textContent=err.message+" Intente nuevamente.";}
    });
  }
  document.addEventListener("DOMContentLoaded",()=>{
    refrescarContador();
    // Solo se invoca 5 s después de mostrar el dashboard; el servidor exige
    // una marca de login reciente y la consume una única vez por sesión.
    if(document.body.classList.contains("vista-dashboard")){
      setTimeout(async()=>{
        try{const d=await get("/avisos/inicio");mostrarPendientes(d.avisos||[]);}
        catch(_){/* El dashboard continúa operativo si el API no responde. */}
      },5000);
    }
    setInterval(refrescarContador,60000);
  });
})();
