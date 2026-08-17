#!/usr/bin/env python3
"""Build a deterministic real-PDF correspondence benchmark without database writes."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import sqlalchemy as sa
REPO_ROOT=Path(__file__).resolve().parents[1];SRC=REPO_ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.models import Paper, PaperCreatorMention, PaperDocument  # noqa:E402
from paperazzi.identity.authorship_evidence import _CORRESPONDENCE_MARKER,_PUBLISHER_NOISE,_find_authors_in_text  # noqa:E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa:E402
from paperazzi.provenance.service import effective_document_role,select_primary_document  # noqa:E402

def _key(paper_id:int)->str:return hashlib.sha256(f'paperazzi-correspondence-v1:{paper_id}'.encode()).hexdigest()
def _source_name(m):return m.display_name or ' '.join(x for x in (m.first_name,m.last_name) if x) or 'Unknown author'

def choose_papers(session,size:int):
    papers=session.query(Paper).filter(Paper.active_in_zotero.is_(True)).all();candidates=[]
    for p in papers:
        d=select_primary_document(session,p.paper_id)
        if d is None or not d.local_path or not Path(d.local_path).is_file():continue
        candidates.append((p,d))
    # Venue-diverse first pass, deterministic within venue, then deterministic fill.
    by_venue={}
    for p,d in candidates:
        venue=(p.venue or '<NO VENUE>').strip();row=by_venue.get(venue)
        if row is None or _key(p.paper_id)<_key(row[0].paper_id):by_venue[venue]=(p,d)
    selected=sorted(by_venue.values(),key=lambda row:_key(row[0].paper_id))[:size]
    seen={p.paper_id for p,_ in selected}
    if len(selected)<size:
        for row in sorted(candidates,key=lambda row:_key(row[0].paper_id)):
            if row[0].paper_id not in seen:selected.append(row);seen.add(row[0].paper_id)
            if len(selected)>=size:break
    return selected

def build_case(session,paper,document):
    evidence=extract_pdf_evidence(document.local_path);mentions=session.query(PaperCreatorMention).filter_by(paper_id=paper.paper_id,creator_type='author').order_by(PaperCreatorMention.order_index).all()
    predicted=[];candidate_texts=[]
    for span in evidence.correspondence_candidates:
        raw=span.text;candidate_texts.append(raw)
        explicit=bool(_CORRESPONDENCE_MARKER.search(raw));noisy=bool(_PUBLISHER_NOISE.search(raw))
        if explicit and not noisy:
            for authorship,mention in _find_authors_in_text(session,paper.paper_id,raw):
                name=_source_name(mention)
                if name not in predicted:predicted.append(name)
    role=effective_document_role(session,document)
    return {
        'paper_id':paper.paper_id,'title':paper.title,'doi':paper.doi,'venue':paper.venue,
        'document_id':document.document_id,'document_role':role.role,'file_name':Path(document.local_path).name,
        'page_count':evidence.page_count,'text_status':evidence.text_status,'extraction_error':evidence.error,
        'source_authors':[_source_name(m) for m in mentions],'emails':list(evidence.emails),
        'correspondence_candidates':candidate_texts,'predicted_corresponding_authors':predicted,
        'ground_truth_corresponding_authors':[],'review_status':'UNREVIEWED','review_notes':'',
    }

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--db-path',type=Path,required=True);p.add_argument('--sample-size',type=int,default=80);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.db_path.is_file():print(json.dumps({'error':'database not found'}));return 2
    engine=create_paperazzi_engine(a.db_path);sf=sa.orm.sessionmaker(bind=engine)
    try:
        with sf() as s:
            rows=[build_case(s,paper,doc) for paper,doc in choose_papers(s,max(1,a.sample_size))]
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'schema_version':'correspondence-benchmark-v1','cases':rows},indent=2,ensure_ascii=False),encoding='utf-8')
        summary={'cases':len(rows),'with_candidate':sum(bool(r['correspondence_candidates']) for r in rows),'with_email':sum(bool(r['emails']) for r in rows),'predicted_nonempty':sum(bool(r['predicted_corresponding_authors']) for r in rows),'output':str(a.output)}
        print(json.dumps(summary,indent=2,ensure_ascii=False));return 0
    finally:engine.dispose()
if __name__=='__main__':raise SystemExit(main())
