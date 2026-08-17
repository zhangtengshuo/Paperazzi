"""Read-only sourced author evidence for profile inspection.

This deliberately does not promote affiliation/contact text into canonical profile fields.
It exposes provenance-bearing paper-level evidence so users can inspect what is known and
what remains a candidate before Phase 6 assertion projection.
"""
from __future__ import annotations
from typing import Any
from paperazzi.database.models import Paper
from .models import Authorship, AuthorshipEvidence

def author_sourced_evidence(session:Any,author_id:str,*,limit:int=100)->list[dict[str,Any]]:
    rows=(session.query(AuthorshipEvidence,Authorship,Paper)
          .join(Authorship,Authorship.authorship_id==AuthorshipEvidence.authorship_id)
          .join(Paper,Paper.paper_id==Authorship.paper_id)
          .filter(Authorship.author_id==author_id,Authorship.status=='ACTIVE',AuthorshipEvidence.status.in_(('ACCEPTED','CANDIDATE')))
          .order_by(Paper.publication_year.desc().nullslast(),Paper.paper_id.desc(),AuthorshipEvidence.authorship_evidence_id.desc())
          .limit(min(max(1,limit),500)).all())
    return [{'authorship_evidence_id':e.authorship_evidence_id,'evidence_type':e.evidence_type,'status':e.status,'raw_value':e.raw_value,'score':e.score,'paper_id':p.paper_id,'paper_title':p.title,'year':p.publication_year} for e,_a,p in rows]
