"""Small UI ordering/provenance patch applied after the WoS UI enhancement."""

WOS_PRIORITY_UI_JS = r'''
(function(){
  const previousShowPaper = showPaper;
  showPaper = async function(id){
    await previousShowPaper(id);
    const detail = document.querySelector('.panel.detail');
    if(!detail) return;

    const wosSection = document.getElementById('wos-paper-section');
    const auditHeading = Array.from(detail.querySelectorAll('h3')).find(
      h => h.textContent.trim().startsWith('Local-AI PDF audit')
    );
    const auditSection = auditHeading?.closest('.section');
    if(wosSection && auditSection && wosSection.nextElementSibling !== auditSection){
      detail.insertBefore(wosSection, auditSection);
    }

    const label = Array.from(detail.querySelectorAll('.stat > span')).find(
      x => x.textContent.trim() === 'Current DB corresponding'
    );
    if(label){
      label.textContent = 'Effective corresponding';
      label.title = 'WoS RP is preferred when a linked WoS record maps safely to the source author list; otherwise local PDF/Paperazzi evidence is fallback.';
    }

    const resolution = document.querySelector('.panel.side .wos-resolution-source');
    if(!resolution){
      try{
        const p = await api('/api/papers/' + id);
        const side = document.querySelector('.panel.side');
        if(side && p.correspondence_resolution){
          side.insertAdjacentHTML(
            'beforeend',
            `<div class="stat wos-resolution-source"><span>Correspondence source</span><strong>${esc(p.correspondence_resolution.effective_source||'UNKNOWN')}</strong></div>`
          );
        }
      }catch(_e){}
    }
  };

  // Collection navigation is served as a separate static enhancement so the base
  // dependency-free UI remains small.  The endpoint is registered on the same local
  // FastAPI application; no external network request is involved.
  if(!document.getElementById('paperazzi-collections-ui')){
    const script=document.createElement('script');
    script.id='paperazzi-collections-ui';
    script.src='/api/collections/ui.js';
    script.defer=true;
    document.body.appendChild(script);
  }
})();
'''
