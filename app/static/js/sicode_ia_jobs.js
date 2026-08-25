(()=>{
  const root=document.querySelector('[data-sia-float]');
  const page=document.querySelector('[data-sia-job-page]');
  const activeKey='sicodeIAActiveJob';
  let jobId=(page&&page.dataset.jobId)||localStorage.getItem(activeKey);
  let timer=null;

  function statusUrl(id){return `/coordinacion/analisis-documental/ia/trabajos/${encodeURIComponent(id)}/estado`;}
  function setLight(el,color){if(!el)return;el.classList.remove('amarillo','verde','rojo');el.classList.add(color||'amarillo');}
  function updatePage(d){
    if(!page)return;
    setLight(page.querySelector('[data-job-light]'),d.semaforo);
    const pct=Math.max(0,Math.min(100,Number(d.porcentaje||0)));
    const title=page.querySelector('[data-job-title]'),detail=page.querySelector('[data-job-detail]'),percent=page.querySelector('[data-job-percent]'),bar=page.querySelector('[data-job-bar]'),review=page.querySelector('[data-job-review]');
    if(title) title.textContent=d.semaforo==='verde'?'Análisis terminado':d.semaforo==='rojo'?'Análisis detenido':'SICODE.IA está trabajando';
    if(detail) detail.textContent=d.detalle||'Procesando documentos';
    if(percent) percent.textContent=`${pct}%`;
    if(bar) bar.style.width=`${pct}%`;
    if(review&&d.revision_url){review.href=d.revision_url;review.hidden=false;}
  }
  function updateFloat(d){
    if(!root)return;
    root.classList.add('on');
    setLight(root.querySelector('[data-sia-float-light]'),d.semaforo);
    const pct=Math.max(0,Math.min(100,Number(d.porcentaje||0)));
    const title=root.querySelector('[data-sia-float-title]'),detail=root.querySelector('[data-sia-float-detail]'),bar=root.querySelector('[data-sia-float-bar]'),open=root.querySelector('[data-sia-float-open]');
    if(title) title.textContent=d.semaforo==='verde'?'SICODE.IA terminó':d.semaforo==='rojo'?'SICODE.IA requiere atención':'SICODE.IA trabajando';
    if(detail) detail.textContent=`${pct}% · ${d.detalle||'Procesando'}`;
    if(bar) bar.style.width=`${pct}%`;
    if(open){open.href=d.revision_url||`/coordinacion/analisis-documental/ia/trabajos/${encodeURIComponent(jobId)}`;open.textContent=d.revision_url?'Verificar':'Abrir';}
  }
  async function poll(){
    if(!jobId)return;
    try{
      const r=await fetch(statusUrl(jobId),{headers:{'Accept':'application/json'},credentials:'same-origin'});
      if(r.status===404){localStorage.removeItem(activeKey);if(root)root.classList.remove('on');return;}
      const d=await r.json();
      updatePage(d);updateFloat(d);
      if(d.semaforo==='verde'||d.semaforo==='rojo'){
        clearInterval(timer);timer=null;
      }
    }catch(e){
      if(root){root.classList.add('on');const detail=root.querySelector('[data-sia-float-detail]');if(detail)detail.textContent='Reconectando con el worker…';}
    }
  }
  if(jobId){poll();timer=setInterval(poll,2500);}
  document.addEventListener('click',e=>{
    const close=e.target.closest('[data-sia-float-close]');
    if(close&&root){root.classList.remove('on');}
    const min=e.target.closest('[data-job-minimize]');
    if(min&&jobId)localStorage.setItem(activeKey,jobId);
  });
})();
