"""Small UI override for multi-candidate canonical identity comparison.

Kept separate from the dependency-free base UI so the identity-review workflow can evolve
without turning the main MVP HTML into an unmaintainable block. Loaded after APP_HTML's base
script; this definition intentionally replaces the base showIdentityReview function.
"""

IDENTITY_REVIEW_MULTICANDIDATE_JS = r'''
async function markCanonicalPairDifferent(source,target,reviewId){
  if(!confirm('Record these canonical identities as different people? This pair will be excluded from future similar-name suggestions.'))return;
  try{
    await post('/api/authors/not-same',{source_author_id:source,target_author_id:target,review_item_id:reviewId,notes:'Manual Identity Review UI'});
    showReviews();
  }catch(e){alert(e.message)}
}
async function showIdentityReview(id){
  try{
    const d=await api('/api/reviews/identity/'+id);
    if(d.subject_type==='creator_mention'){
      const m=d.source_mention;
      const cards=(d.candidates||[]).map(a=>`${authorCompareCard(a,'Candidate')}<div class="review-actions"><button class="primary" ${a.same_paper_conflict?'disabled':''} onclick="linkCandidate(${id},'${esc(a.author_id)}')">Link mention to this identity</button><button class="danger" onclick="notSame(${id},'${esc(a.author_id)}')">Not same person</button><button onclick="showAuthor('${encodeURIComponent(a.author_id)}')">Open full profile</button></div>`).join('');
      app.innerHTML=`<div class="back" onclick="showReviews()">← Identity Review</div><div class="panel detail"><h2>Compare source mention</h2><div class="review-card"><h3>${esc(m.source_name)}</h3><div class="meta"><span>Paperazzi paper ID ${m.paper_id}</span><span>author position ${m.order_index+1}</span><span>${esc(d.reason_code||'')}</span></div><div class="paper-mini">${esc(m.paper_title||'')}</div></div><div class="explain">Similarity is a review aid only. A name match never auto-merges people. Compare name variants, publications and coauthors before linking.</div>${cards||'<div class="empty">No similar canonical author candidates found.</div>'}<div class="review-actions"><button onclick="createSeparate(${id})">Create separate identity</button></div></div>`;
      return;
    }
    if(d.subject_type==='author'&&d.source_author){
      const left=d.source_author;
      const candidates=d.candidates||[];
      const candidateCards=candidates.map((right,index)=>`${authorCompareCard(right,'Candidate '+(index+1))}<div class="review-actions">${right.same_paper_conflict?'<span class="badge warn">Merge blocked: identities co-occur on a paper</span>':`<button class="primary" onclick="mergePair('${esc(left.author_id)}','${esc(right.author_id)}',${id})">Merge source → candidate</button><button class="primary" onclick="mergePair('${esc(right.author_id)}','${esc(left.author_id)}',${id})">Merge candidate → source</button>`}<button class="danger" onclick="markCanonicalPairDifferent('${esc(left.author_id)}','${esc(right.author_id)}',${id})">Different people</button><button onclick="showAuthor('${encodeURIComponent(right.author_id)}')">Open candidate profile</button></div>`).join('');
      app.innerHTML=`<div class="back" onclick="showReviews()">← Identity Review</div><div class="panel detail"><h2>Possible duplicate canonical identities</h2><div class="explain">The queue provides one entry per source identity, while this page lists several similar people. Similarity never performs an automatic merge. Compare every recorded spelling, publications, coauthors and external IDs. “Different people” is a persistent manual decision, so the pair will not be suggested again. Same-paper co-occurrence is shown but cannot be merged.</div>${authorCompareCard(left,'Source identity')}<div class="section"><h3>Similar identities (${candidates.length})</h3>${candidateCards||'<div class="empty">No current similar candidates.</div>'}</div></div>`;
      return;
    }
    app.innerHTML=`<div class="back" onclick="showReviews()">← Identity Review</div><div class="panel detail"><h2>${esc(d.queue_type)}</h2><pre>${esc(JSON.stringify(d,null,2))}</pre></div>`;
  }catch(e){fail(e)}
}
'''
