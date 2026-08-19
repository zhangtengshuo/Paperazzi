"""Zotero-style collection navigation enhancement for the dependency-free Web UI."""

COLLECTIONS_UI_JS = r'''
(function(){
  if(window.__paperazziCollectionsInstalled) return;
  window.__paperazziCollectionsInstalled=true;

  const style=document.createElement('style');
  style.textContent=`
    .library-layout{display:grid;grid-template-columns:minmax(240px,310px) minmax(0,1fr);gap:14px;align-items:start}
    .collection-sidebar{position:sticky;top:65px;max-height:calc(100vh - 88px);overflow:auto;background:#fff;border:1px solid #e2e7ec;border-radius:11px;box-shadow:0 2px 8px rgba(0,0,0,.04)}
    .collection-sidebar-head{padding:12px 12px 8px;border-bottom:1px solid #edf0f3;display:flex;justify-content:space-between;align-items:center;gap:8px}
    .collection-tree{padding:6px 5px 10px;font-size:13px;user-select:none}
    .collection-node-line{display:flex;align-items:center;gap:4px;min-height:29px;border-radius:6px;padding-right:6px;cursor:pointer}
    .collection-node-line:hover{background:#f4f7f9}.collection-node-line.selected{background:#e8f0f8;color:#173b57;font-weight:650}
    .collection-toggle{width:20px;flex:0 0 20px;text-align:center;color:#65727d;cursor:pointer}.collection-toggle.empty{visibility:hidden}
    .collection-icon{width:17px;text-align:center;color:#667985}.collection-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
    .collection-count{font-size:11px;color:#78838d;min-width:24px;text-align:right}.collection-children{margin-left:17px}
    .collection-pseudo{font-weight:600}.collection-orphan-title{padding:8px 7px 3px;color:#8b641e;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
    .collection-breadcrumb{display:flex;gap:4px;align-items:center;flex-wrap:wrap;font-size:12px;color:#69737d}.collection-crumb{cursor:pointer}.collection-crumb:hover{text-decoration:underline}
    .collection-path-chip{display:inline-flex;gap:3px;align-items:center;border:1px solid #d8dfe5;background:#f8fafb;border-radius:999px;padding:3px 8px;margin:2px 4px 2px 0;font-size:12px}
    .collection-detail-section .tag-chip{display:inline-block;border:1px solid #d8dfe5;background:#fff;border-radius:999px;padding:2px 7px;margin:2px 4px 2px 0;font-size:11px}
    .collection-sidebar-toggle{display:none;border:1px solid #ccd5dd;background:#fff;border-radius:7px;padding:6px 9px}
    @media(max-width:900px){.library-layout{grid-template-columns:1fr}.collection-sidebar{position:relative;top:auto;max-height:360px}.collection-sidebar.collapsed .collection-tree{display:none}.collection-sidebar-toggle{display:inline-block}.collection-sidebar.collapsed{max-height:none}.collection-sidebar.collapsed .collection-sidebar-head{border-bottom:0}}
  `;
  document.head.appendChild(style);

  const EXPAND_KEY='paperazzi.collection.expanded.v1';
  const SELECT_KEY='paperazzi.collection.selection.v1';
  let treeCache=null;
  let collectionSelection={kind:'all',library_id:1,key:null,name:'All papers',path:[]};
  let expanded=new Set();
  try{expanded=new Set(JSON.parse(localStorage.getItem(EXPAND_KEY)||'[]'))}catch(_e){}
  try{
    const saved=JSON.parse(localStorage.getItem(SELECT_KEY)||'null');
    if(saved && ['all','unfiled','collection'].includes(saved.kind)) collectionSelection=saved;
  }catch(_e){}

  function persistState(){
    try{localStorage.setItem(EXPAND_KEY,JSON.stringify([...expanded]));localStorage.setItem(SELECT_KEY,JSON.stringify(collectionSelection))}catch(_e){}
  }
  async function loadTree(force=false){
    if(treeCache&&!force)return treeCache;
    treeCache=await api(`/api/collections/tree?library_id=${collectionSelection.library_id||1}&include_empty=true`);
    return treeCache;
  }
  function selected(kind,key=null){return collectionSelection.kind===kind&&(kind!=='collection'||collectionSelection.key===key)}
  function expandAncestors(path){for(const p of path||[])expanded.add(p.collection_key);persistState()}
  function toggleCollection(key,event){event?.stopPropagation();expanded.has(key)?expanded.delete(key):expanded.add(key);persistState();showPapers(paperOffset)}

  function nodeHtml(node){
    const kids=node.children||[],open=expanded.has(node.collection_key),sel=selected('collection',node.collection_key),
      toggle=kids.length?`<span class="collection-toggle" onclick="toggleCollection('${esc(node.collection_key)}',event)">${open?'▾':'▸'}</span>`:'<span class="collection-toggle empty">▸</span>',
      nested=kids.length&&open?`<div class="collection-children">${kids.map(nodeHtml).join('')}</div>`:'';
    return `<div class="collection-node"><div class="collection-node-line ${sel?'selected':''}" title="${esc(node.name)}" onclick="selectCollection('${esc(node.collection_key)}')">${toggle}<span class="collection-icon">▰</span><span class="collection-name">${esc(node.name)}</span><span class="collection-count" title="Direct active papers">${esc(node.active_paper_count)}</span></div>${nested}</div>`;
  }
  function treeHtml(tree){
    const allSel=selected('all'),unfiledSel=selected('unfiled'),orphans=tree.orphaned||[];
    return `<div class="collection-sidebar" id="collection-sidebar"><div class="collection-sidebar-head"><strong>Zotero Library</strong><button class="collection-sidebar-toggle" onclick="document.getElementById('collection-sidebar')?.classList.toggle('collapsed')">Folders</button></div><div class="collection-tree">
      <div class="collection-node-line collection-pseudo ${allSel?'selected':''}" onclick="selectAllPapers()"><span class="collection-toggle empty">▸</span><span class="collection-icon">▤</span><span class="collection-name">All papers</span><span class="collection-count">${esc(tree.all_papers?.active_paper_count||0)}</span></div>
      <div class="collection-node-line collection-pseudo ${unfiledSel?'selected':''}" onclick="selectUnfiled()"><span class="collection-toggle empty">▸</span><span class="collection-icon">□</span><span class="collection-name">Unfiled</span><span class="collection-count">${esc(tree.unfiled?.active_paper_count||0)}</span></div>
      ${(tree.roots||[]).map(nodeHtml).join('')}
      ${orphans.length?`<div class="collection-orphan-title">Missing parent / orphaned</div>${orphans.map(nodeHtml).join('')}`:''}
    </div></div>`;
  }
  function breadcrumbHtml(){
    if(collectionSelection.kind==='all')return '<span>All papers</span>';
    if(collectionSelection.kind==='unfiled')return '<span>Unfiled</span>';
    const parts=(collectionSelection.path||[]).map((p,i)=>`<span class="collection-crumb" onclick="selectCollection('${esc(p.collection_key)}')">${esc(p.name)}</span>${i<(collectionSelection.path||[]).length-1?'<span>›</span>':''}`);
    return parts.join('');
  }

  window.toggleCollection=toggleCollection;
  window.selectAllPapers=function(){collectionSelection={kind:'all',library_id:collectionSelection.library_id||1,key:null,name:'All papers',path:[]};persistState();showPapers(0)};
  window.selectUnfiled=function(){collectionSelection={kind:'unfiled',library_id:collectionSelection.library_id||1,key:null,name:'Unfiled',path:[]};persistState();showPapers(0)};
  window.selectCollection=async function(key){
    try{
      const tree=await loadTree(),stack=[...(tree.roots||[]),...(tree.orphaned||[])];let found=null;
      while(stack.length){const n=stack.pop();if(n.collection_key===key){found=n;break}stack.push(...(n.children||[]))}
      if(!found)throw new Error('Collection '+key+' is not in the current Zotero catalog');
      collectionSelection={kind:'collection',library_id:found.library_id,key:found.collection_key,name:found.name,path:found.path||[]};expandAncestors(found.path||[]);persistState();showPapers(0);
    }catch(e){fail(e)}
  };

  const baseShowPapers=showPapers;
  showPapers=async function(offset=paperOffset){
    paperOffset=Math.max(0,offset);
    try{
      const tree=await loadTree();
      let d,title,subtitle;
      if(collectionSelection.kind==='all'){
        d=await api(`/api/papers?limit=${PAGE_SIZE}&offset=${paperOffset}`);title='Papers';subtitle=`${d.total} in Zotero`;
      }else if(collectionSelection.kind==='unfiled'){
        d=await api(`/api/collections/unfiled/papers?library_id=${collectionSelection.library_id}&limit=${PAGE_SIZE}&offset=${paperOffset}`);title='Unfiled';subtitle=`${d.total} active papers without a collection`;
      }else{
        d=await api(`/api/collections/${encodeURIComponent(collectionSelection.key)}/papers?library_id=${collectionSelection.library_id}&include_descendants=false&limit=${PAGE_SIZE}&offset=${paperOffset}`);title=collectionSelection.name;subtitle=`${d.total} direct papers`;
      }
      app.innerHTML=`<div class="library-layout">${treeHtml(tree)}<div class="panel"><div class="toolbar"><div><strong>${esc(title)}</strong><div class="collection-breadcrumb">${breadcrumbHtml()}</div></div><span class="muted">${esc(subtitle)}</span></div>${pager(d.total,paperOffset,'papers',true)}<div class="list">${(d.items||[]).map(paperRow).join('')||'<div class="empty">No papers in this view</div>'}</div>${pager(d.total,paperOffset,'papers')}</div></div>`;
    }catch(e){
      if(String(e.message||'').includes('zotero_collections')){await baseShowPapers(offset);return}
      fail(e);
    }
  };

  const previousShowPaper=showPaper;
  showPaper=async function(id){
    await previousShowPaper(id);
    try{
      const org=await api('/api/papers/'+id+'/organization');
      const detail=document.querySelector('.panel.detail'); if(!detail)return;
      const paths=(org.collection_paths||[]).map(path=>`<span class="collection-path-chip">${path.map(x=>esc(x.name||x.collection_key)).join(' › ')}</span>`).join('');
      const tags=(org.tags||[]).map(t=>`<span class="tag-chip">${esc(t.name)}</span>`).join('');
      const section=`<div class="section collection-detail-section"><h3>Zotero organization</h3><div class="explain">Read-only organization data from the current Zotero scan. Collections and tags are separate dimensions.</div><div class="stat"><span>Collections</span><strong>${(org.collections||[]).length}</strong></div><div>${paths||'<span class="muted">Unfiled</span>'}</div>${tags?`<div class="section"><h3>Tags</h3><div>${tags}</div></div>`:''}</div>`;
      const firstSection=detail.querySelector('.section');
      if(firstSection)firstSection.insertAdjacentHTML('beforebegin',section);else detail.insertAdjacentHTML('beforeend',section);
      const side=document.querySelector('.panel.side');
      if(side)side.insertAdjacentHTML('beforeend',`<div class="stat"><span>Zotero collections</span><strong>${esc((org.collections||[]).length)}</strong></div>`);
    }catch(_e){}
  };

  loadTree().then(tree=>{
    if(collectionSelection.kind==='collection'){
      const stack=[...(tree.roots||[]),...(tree.orphaned||[])];let found=null;
      while(stack.length){const n=stack.pop();if(n.collection_key===collectionSelection.key){found=n;break}stack.push(...(n.children||[]))}
      if(found){collectionSelection={kind:'collection',library_id:found.library_id,key:found.collection_key,name:found.name,path:found.path||[]};expandAncestors(found.path||[])}
      else collectionSelection={kind:'all',library_id:tree.library_id,key:null,name:'All papers',path:[]};
    }else collectionSelection.library_id=tree.library_id;
    persistState();
    showPapers(paperOffset);
  }).catch(()=>{});
})();
'''

__all__ = ["COLLECTIONS_UI_JS"]
