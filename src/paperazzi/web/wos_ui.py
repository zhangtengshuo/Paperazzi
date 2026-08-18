"""Browser UI enhancement for the independent WoS background corpus."""

WOS_UI_JS = r'''
(function(){
  const tabs=document.querySelector('.tabs');
  if(tabs && !document.getElementById('wos-tab')){
    tabs.insertAdjacentHTML('beforeend','<button id="wos-tab" onclick="showWosCorpus()">WoS Corpus</button>');
  }

  function wosBadge(status){
    if(status==='WOS_MATCHED') return '<span class="badge ok">WoS structured</span>';
    if(status==='WOS_NOT_IN_LOCAL_CORPUS') return '<span class="badge warn">No local WoS record</span>';
    if(status==='WOS_MATCH_AMBIGUOUS') return '<span class="badge warn">WoS match ambiguous</span>';
    return '<span class="badge">WoS not checked</span>';
  }
  function grouped(items,key){
    const out={}; for(const x of items||[]){const k=x[key]||'Other';(out[k]??=[]).push(x)} return out;
  }
  function renderWosPaper(w){
    if(w.status!=='WOS_MATCHED'){
      const text=w.status==='WOS_NOT_IN_LOCAL_CORPUS'
        ? 'This paper has no accepted record in the currently imported local WoS corpus. This does not mean the article is absent from Web of Science. Corresponding-author, affiliation, or reference information shown from the local PDF remains fallback/provisional evidence until a WoS record is linked.'
        : w.status==='WOS_MATCH_AMBIGUOUS'
        ? 'The current local WoS corpus contains ambiguous candidates. No WoS record has been promoted for this paper.'
        : 'WoS information has not yet been resolved for this paper. Existing Zotero/PDF functions remain fully usable.';
      return `<div class="section" id="wos-paper-section"><h3>Web of Science ${wosBadge(w.status)}</h3><div class="explain">${esc(text)}</div>${w.reason?`<div class="meta">State: ${esc(w.reason)}</div>`:''}</div>`;
    }
    const r=w.record||{}, corr=(r.corresponding_authors||[]).map(a=>a.full_name||a.au_name||a.raw_member_name),
      kw=grouped(r.keywords||[],'keyword_type'), cl=grouped(r.classifications||[],'namespace'), funding=r.funding||{};
    const keywordHtml=Object.entries(kw).map(([k,v])=>`<div class="stat"><span>${esc(k)}</span><strong>${v.map(x=>esc(x.keyword)).join('; ')}</strong></div>`).join('');
    const classHtml=Object.entries(cl).map(([k,v])=>`<div class="stat"><span>${esc(k)}</span><strong>${v.map(x=>esc(x.value)).join('; ')}</strong></div>`).join('');
    return `<div class="section" id="wos-paper-section">
      <h3>Web of Science ${wosBadge(w.status)}</h3>
      <div class="explain">Preferred structured scholarly metadata from the independently imported local WoS corpus. Zotero and PDF evidence remain separate provenance sources.</div>
      <div class="stat"><span>WoS accession</span><strong>${esc(r.ut||w.wos_ut)}</strong></div>
      <div class="stat"><span>Match</span><strong>${esc(w.match_method||'')} ${w.match_score!=null?esc(Number(w.match_score).toFixed(3)):''}</strong></div>
      <div class="stat"><span>Corresponding authors</span><strong>${esc(corr.join(', ')||'None recorded')}</strong></div>
      <div class="stat"><span>E-mails</span><strong>${esc((r.emails||[]).join('; ')||'—')}</strong></div>
      <div class="stat"><span>Organizations</span><strong>${esc((r.organizations||[]).join('; ')||'—')}</strong></div>
      <div class="stat"><span>WoS citations / total</span><strong>${esc(r.times_cited_wos??'—')} / ${esc(r.times_cited_total??'—')}</strong></div>
      <div class="stat"><span>References</span><strong>${esc(r.reference_count||0)} (${esc(r.resolved_reference_count||0)} resolved inside local WoS corpus)</strong></div>
      ${keywordHtml}${classHtml}
      ${funding.funding_agencies_raw?`<div class="section"><h3>Funding</h3><div class="evidence-raw">${esc(funding.funding_agencies_raw)}</div>${funding.funding_text_raw?`<div class="evidence-raw">${esc(funding.funding_text_raw)}</div>`:''}</div>`:''}
      ${r.abstract?`<div class="section"><h3>WoS abstract</h3><div class="evidence-raw">${esc(r.abstract)}</div></div>`:''}
      <div class="section"><button onclick="showWosReferences('${esc(r.ut||w.wos_ut)}')">Show WoS cited references</button></div>
    </div>`;
  }

  const baseShowPaper=showPaper;
  showPaper=async function(id){
    await baseShowPaper(id);
    try{
      const w=await api('/api/papers/'+id+'/wos');
      const detail=document.querySelector('.panel.detail');
      if(detail) detail.insertAdjacentHTML('beforeend',renderWosPaper(w));
      const side=document.querySelector('.panel.side');
      if(side) side.insertAdjacentHTML('beforeend',`<div class="stat"><span>WoS</span><strong>${wosBadge(w.status)}</strong></div>`);
    }catch(e){
      const detail=document.querySelector('.panel.detail');
      if(detail) detail.insertAdjacentHTML('beforeend',`<div class="section"><h3>Web of Science</h3><div class="error">${esc(e.message)}</div></div>`);
    }
  };

  window.showWosReferences=async function(ut){
    try{
      const d=await api('/api/wos/records/'+encodeURIComponent(ut)+'/references?limit=500');
      const section=document.getElementById('wos-paper-section'); if(!section)return;
      const old=document.getElementById('wos-reference-list'); if(old)old.remove();
      const rows=(d.items||[]).map(x=>`<div class="evidence-row"><span class="badge">${x.order_index+1}</span> ${x.target_ut?`<span class="badge ok">local WoS ${esc(x.target_ut)}</span>`:'<span class="badge">external/unresolved</span>'}<div class="evidence-raw">${esc(x.raw_reference)}</div></div>`).join('');
      section.insertAdjacentHTML('beforeend',`<div class="section" id="wos-reference-list"><h3>Cited references</h3>${rows||'<div class="muted">No references recorded.</div>'}</div>`);
    }catch(e){fail(e)}
  };

  window.showWosCorpus=async function(){
    try{
      const [s,c,f]=await Promise.all([api('/api/wos/stats'),api('/api/wos/coverage'),api('/api/wos/frontier?limit=30')]);
      if(!s.available){
        app.innerHTML=`<div class="panel detail"><h2>WoS Background Corpus</h2><div class="explain">No local WoS database is configured yet. This is a normal state and does not block Zotero or PDF workflows. Import Clarivate Plain Text / Full Record and Cited References files with <code>paperazzi-wos import ...</code>.</div></div>`; return;
      }
      const frontier=(f.items||[]).map(x=>`<div class="row"><div class="title">${esc(x.cited_doi)}</div><div class="meta"><span>cited by ${esc(x.cited_by_count)} local WoS records</span><span>${esc(x.cited_author||'')}</span><span>${esc(x.cited_year||'')}</span><span>${esc(x.cited_source||'')}</span></div></div>`).join('');
      app.innerHTML=`<div class="panel"><div class="toolbar"><strong>WoS Background Corpus</strong><span class="muted">Independent of Zotero</span></div>
        <div class="detail"><div class="grid"><div><div class="stat"><span>WoS records</span><strong>${esc(s.records)}</strong></div><div class="stat"><span>Authors</span><strong>${esc(s.authors)}</strong></div><div class="stat"><span>Cited references</span><strong>${esc(s.cited_references)}</strong></div><div class="stat"><span>Resolved citation edges</span><strong>${esc(s.resolved_citation_edges)}</strong></div></div><div><div class="stat"><span>Zotero active papers</span><strong>${esc(c.active_zotero_papers)}</strong></div><div class="stat"><span>Accepted WoS links</span><strong>${esc(c.matched)}</strong></div><div class="stat"><span>Without accepted link</span><strong>${esc(c.without_accepted_local_wos_link)}</strong></div><div class="stat"><span>Coverage</span><strong>${(Number(c.coverage_fraction||0)*100).toFixed(1)}%</strong></div></div></div>
        <div class="section"><h3>Search the WoS corpus</h3><div class="search"><input id="wos-q" placeholder="Title, DOI, UT, author, journal, keyword" onkeydown="if(event.key==='Enter')runWosSearch()"><button onclick="runWosSearch()">Search</button></div><div id="wos-search-results"></div></div>
        <div class="section"><h3>Citation frontier</h3><div class="explain">Frequently cited DOI targets whose Full Records are not yet in the local WoS corpus. Use this to guide the next broad/manual WoS export; filling all targets is not required.</div><div class="list">${frontier||'<div class="empty">No unresolved DOI frontier.</div>'}</div></div></div></div>`;
    }catch(e){fail(e)}
  };

  window.runWosSearch=async function(){
    const q=(document.getElementById('wos-q')?.value||'').trim(); if(!q)return;
    try{
      const d=await api('/api/wos/search?q='+encodeURIComponent(q)+'&limit=100'), target=document.getElementById('wos-search-results');
      if(!target)return;
      target.innerHTML=`<div class="list">${(d.items||[]).map(r=>`<div class="row" onclick="showWosRecord('${esc(r.ut)}')"><div class="title">${esc(r.title||r.ut)}</div><div class="meta"><span>${esc(r.publication_year||'')}</span><span>${esc(r.source_title||'')}</span><span>${esc(r.doi||'')}</span><span>${esc(r.ut)}</span></div></div>`).join('')||'<div class="empty">No WoS records matched.</div>'}</div>`;
    }catch(e){fail(e)}
  };

  window.showWosRecord=async function(ut){
    try{
      const r=await api('/api/wos/records/'+encodeURIComponent(ut)), corr=[] , seen=new Set();
      for(const g of r.correspondence_groups||[])for(const m of g.members||[]){const k=m.wos_author_id||m.normalized_member_name||m.raw_member_name;if(!seen.has(k)){seen.add(k);corr.push(m.full_name||m.au_name||m.raw_member_name)}}
      const kw=(r.keywords||[]).map(x=>`${x.keyword_type}: ${x.keyword}`).join('; '), cls=(r.classifications||[]).map(x=>`${x.namespace}: ${x.value}`).join('; ');
      app.innerHTML=`<div class="back" onclick="showWosCorpus()">← WoS Corpus</div><div class="panel detail"><h2>${esc(r.title||r.ut)}</h2><div class="meta"><span>${esc(r.ut)}</span><span>${esc(r.publication_year||'')}</span><span>${esc(r.source_title||'')}</span><span>${esc(r.doi||'')}</span></div><div class="section"><h3>Authors</h3>${(r.authors||[]).map(a=>`<div class="author-line">${a.order_index+1}. ${esc(a.full_name||a.au_name)}</div>`).join('')}</div><div class="stat"><span>Corresponding authors</span><strong>${esc(corr.join(', ')||'None recorded')}</strong></div><div class="stat"><span>E-mails</span><strong>${esc((r.emails||[]).join('; ')||'—')}</strong></div><div class="stat"><span>Organizations</span><strong>${esc((r.organizations||[]).join('; ')||'—')}</strong></div><div class="stat"><span>Keywords</span><strong>${esc(kw||'—')}</strong></div><div class="stat"><span>Classifications</span><strong>${esc(cls||'—')}</strong></div><div class="stat"><span>References</span><strong>${esc(r.reference_count||0)} / ${esc(r.resolved_reference_count||0)} resolved locally</strong></div>${r.funding?.funding_agencies_raw?`<div class="section"><h3>Funding</h3><div class="evidence-raw">${esc(r.funding.funding_agencies_raw)}</div><div class="evidence-raw">${esc(r.funding.funding_text_raw||'')}</div></div>`:''}${r.abstract?`<div class="section"><h3>Abstract</h3><div class="evidence-raw">${esc(r.abstract)}</div></div>`:''}</div>`;
    }catch(e){fail(e)}
  };
})();
'''
