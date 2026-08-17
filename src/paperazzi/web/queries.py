"""Read-oriented Phase 5 query/service layer.

Paper author lists always originate from `paper_creator_mentions`; canonical identity is
an optional projection.  Unresolved authors therefore remain visible and queryable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlalchemy as sa

from paperazzi.database.models import Paper, PaperCreatorMention, PaperDocument
from paperazzi.identity.models import (
    Author, AuthorExternalID, AuthorIdentityMembership, AuthorNameVariant,
    Authorship, ResolutionReviewQueue,
)

class NotFoundError(LookupError): pass
class PdfUnavailableError(LookupError): pass

class PaperazziQueryService:
    def __init__(self, session: Any): self.session = session

    @staticmethod
    def _name(m: PaperCreatorMention) -> str:
        if m.display_name: return m.display_name
        return " ".join(x for x in (m.first_name, m.last_name) if x) or "Unknown author"

    def _paper_authors(self, paper_id: int) -> list[dict[str, Any]]:
        ms = (self.session.query(PaperCreatorMention)
              .filter_by(paper_id=paper_id, creator_type="author")
              .order_by(PaperCreatorMention.order_index, PaperCreatorMention.creator_mention_id).all())
        if not ms: return []
        ids = [m.creator_mention_id for m in ms]
        memberships = {r.creator_mention_id:r for r in self.session.query(AuthorIdentityMembership).filter(
            AuthorIdentityMembership.creator_mention_id.in_(ids), AuthorIdentityMembership.status=="ACCEPTED").all()}
        author_ids = {r.author_id for r in memberships.values()}
        authors = {a.author_id:a for a in self.session.query(Author).filter(Author.author_id.in_(author_ids)).all()} if author_ids else {}
        auths = {r.creator_mention_id:r for r in self.session.query(Authorship).filter(
            Authorship.creator_mention_id.in_(ids), Authorship.status=="ACTIVE").all()}
        first_id = min(ms, key=lambda m:(m.order_index,m.creator_mention_id)).creator_mention_id
        out=[]
        for m in ms:
            mem=memberships.get(m.creator_mention_id); a=authors.get(mem.author_id) if mem else None; rel=auths.get(m.creator_mention_id)
            roles=[]
            if m.creator_mention_id==first_id: roles.append("FIRST")
            if rel is not None and rel.is_corresponding_author: roles.append("CORRESPONDING")
            if not roles: roles=["ORDINARY"]
            out.append({"creator_mention_id":m.creator_mention_id,"order_index":m.order_index,"source_name":self._name(m),
                        "source_creator_id":m.source_creator_id,"author_id":None if a is None else a.author_id,
                        "preferred_name":None if a is None else a.preferred_name,"identity_status":"RESOLVED" if a else "UNRESOLVED",
                        "roles":roles,"corresponding_status":"UNKNOWN" if rel is None else rel.corresponding_status})
        return out

    def _pdf_state(self, paper_id:int)->dict[str,Any]:
        r=(self.session.query(PaperDocument).filter(PaperDocument.paper_id==paper_id,PaperDocument.present_in_last_scan.is_(True))
           .order_by(sa.case((PaperDocument.availability_status=="PDF_AVAILABLE",0),else_=1),PaperDocument.document_id).first())
        if r is None:return {"status":"NONE","document_id":None,"available":False}
        return {"status":r.availability_status or "UNKNOWN","document_id":r.document_id,
                "available":r.availability_status=="PDF_AVAILABLE" and bool(r.local_path)}

    def _paper_summary(self,p:Paper)->dict[str,Any]:
        aa=self._paper_authors(p.paper_id); first=next((a for a in aa if "FIRST" in a["roles"]),None)
        return {"paper_id":p.paper_id,"title":p.title,"doi":p.doi,"year":p.publication_year,"venue":p.venue,"item_type":p.item_type,
                "first_author":None if first is None else first["source_name"],"first_author_resolved":bool(first and first["author_id"]),
                "corresponding_authors":[a["source_name"] for a in aa if "CORRESPONDING" in a["roles"]],"author_count":len(aa),"pdf":self._pdf_state(p.paper_id)}

    def list_papers(self,*,q:str|None=None,year:int|None=None,venue:str|None=None,pdf_available:bool|None=None,limit:int=50,offset:int=0)->dict[str,Any]:
        x=self.session.query(Paper).filter(Paper.active_in_zotero.is_(True))
        if q:
            pat=f"%{q.strip().casefold()}%"; x=x.filter(sa.or_(sa.func.lower(sa.func.coalesce(Paper.title,"" )).like(pat),
                sa.func.lower(sa.func.coalesce(Paper.doi,"" )).like(pat),sa.func.lower(sa.func.coalesce(Paper.venue,"" )).like(pat)))
        if year is not None:x=x.filter(Paper.publication_year==year)
        if venue:x=x.filter(sa.func.lower(sa.func.coalesce(Paper.venue,""))==venue.casefold())
        if pdf_available is not None:
            exists=sa.exists().where(sa.and_(PaperDocument.paper_id==Paper.paper_id,PaperDocument.present_in_last_scan.is_(True),PaperDocument.availability_status=="PDF_AVAILABLE"))
            x=x.filter(exists if pdf_available else ~exists)
        total=x.count(); rows=(x.order_by(Paper.publication_year.desc().nullslast(),Paper.paper_id.desc()).offset(max(0,offset)).limit(min(max(1,limit),200)).all())
        return {"total":total,"items":[self._paper_summary(r) for r in rows]}

    def get_paper(self,paper_id:int)->dict[str,Any]:
        p=self.session.get(Paper,paper_id)
        if p is None:raise NotFoundError(f"paper {paper_id} does not exist")
        d=self._paper_summary(p); d.update(publication_date_text=p.publication_date_text,active_in_zotero=p.active_in_zotero,authors=self._paper_authors(paper_id)); return d

    def list_authors(self,*,q:str|None=None,limit:int=50,offset:int=0)->dict[str,Any]:
        x=self.session.query(Author).filter(Author.status=="ACTIVE")
        if q:
            pat=f"%{q.strip().casefold()}%"
            variant_ids=(self.session.query(AuthorNameVariant.author_id).filter(sa.or_(sa.func.lower(AuthorNameVariant.raw_name).like(pat),
                sa.func.lower(AuthorNameVariant.normalized_name).like(pat),sa.func.lower(sa.func.coalesce(AuthorNameVariant.search_form,"" )).like(pat))).subquery())
            x=x.filter(sa.or_(sa.func.lower(sa.func.coalesce(Author.preferred_name,"" )).like(pat),Author.author_id.in_(sa.select(variant_ids.c.author_id))))
        total=x.count(); rows=(x.order_by(sa.func.lower(sa.func.coalesce(Author.preferred_name,"")),Author.author_id).offset(max(0,offset)).limit(min(max(1,limit),200)).all())
        items=[]
        for a in rows:
            base=self.session.query(Authorship).filter_by(author_id=a.author_id,status="ACTIVE")
            pc=base.count(); fc=base.filter_by(is_first_author=True).count(); cc=base.filter_by(is_corresponding_author=True).count()
            items.append({"author_id":a.author_id,"preferred_name":a.preferred_name,"paper_count":pc,"first_author_count":fc,
                          "corresponding_author_count":cc,"enrichment_priority":bool(fc or cc),"locked":a.locked})
        return {"total":total,"items":items}

    def get_author_publications(self,author_id:str)->list[dict[str,Any]]:
        rows=(self.session.query(Authorship,Paper).join(Paper,Paper.paper_id==Authorship.paper_id)
              .filter(Authorship.author_id==author_id,Authorship.status=="ACTIVE").order_by(Paper.publication_year.desc().nullslast(),Paper.paper_id.desc()).all())
        out=[]
        for rel,p in rows:
            roles=[r for r,f in (("FIRST",rel.is_first_author),("CORRESPONDING",rel.is_corresponding_author)) if f] or ["ORDINARY"]
            out.append({"paper_id":p.paper_id,"title":p.title,"year":p.publication_year,"venue":p.venue,"doi":p.doi,"order_index":rel.order_index,"roles":roles,"pdf":self._pdf_state(p.paper_id)})
        return out

    def get_coauthors(self,author_id:str,*,limit:int=100)->list[dict[str,Any]]:
        pids=[p for (p,) in self.session.query(Authorship.paper_id).filter_by(author_id=author_id,status="ACTIVE").distinct().all()]
        if not pids:return []
        rows=(self.session.query(Authorship.author_id,sa.func.count(sa.distinct(Authorship.paper_id))).filter(Authorship.paper_id.in_(pids),Authorship.status=="ACTIVE",Authorship.author_id!=author_id)
              .group_by(Authorship.author_id).order_by(sa.func.count(sa.distinct(Authorship.paper_id)).desc()).limit(min(max(1,limit),500)).all())
        ids=[r[0] for r in rows]; amap={a.author_id:a for a in self.session.query(Author).filter(Author.author_id.in_(ids)).all()} if ids else {}
        return [{"author_id":aid,"preferred_name":amap.get(aid).preferred_name if amap.get(aid) else None,"shared_papers":int(n)} for aid,n in rows]

    def get_author(self,author_id:str)->dict[str,Any]:
        a=self.session.get(Author,author_id)
        if a is None:raise NotFoundError(f"author {author_id} does not exist")
        vs=self.session.query(AuthorNameVariant).filter_by(author_id=author_id).order_by(AuthorNameVariant.name_variant_id).all()
        ex=self.session.query(AuthorExternalID).filter_by(author_id=author_id,status="ACCEPTED").order_by(AuthorExternalID.namespace).all()
        pubs=self.get_author_publications(author_id); first=sum("FIRST" in p["roles"] for p in pubs); corr=sum("CORRESPONDING" in p["roles"] for p in pubs)
        return {"author_id":a.author_id,"preferred_name":a.preferred_name,"normalized_name":a.normalized_name,"status":a.status,
                "merged_into_author_id":a.merged_into_author_id,"locked":a.locked,
                "name_variants":[{"raw_name":v.raw_name,"variant_type":v.variant_type,"provenance":v.provenance} for v in vs],
                "external_ids":[{"namespace":e.namespace,"value":e.normalized_value,"source":e.source} for e in ex],
                "paper_count":len(pubs),"first_author_count":first,"corresponding_author_count":corr,"enrichment_priority":bool(first or corr),
                "publications":pubs,"coauthors":self.get_coauthors(author_id)}

    def list_identity_review_queue(self,*,limit:int=100)->list[dict[str,Any]]:
        rows=self.session.query(ResolutionReviewQueue).filter(ResolutionReviewQueue.status=="OPEN",ResolutionReviewQueue.queue_type.in_(["AMBIGUOUS_AUTHOR_IDENTITY","IDENTITY_CONFLICT","UNRESOLVED_CORRESPONDING_AUTHOR"])).all(); out=[]
        for r in rows:
            role=100 if r.queue_type=="UNRESOLVED_CORRESPONDING_AUTHOR" else 0; name=None; pid=None
            if r.subject_type=="creator_mention":
                try:m=self.session.get(PaperCreatorMention,int(r.subject_id))
                except (TypeError,ValueError):m=None
                if m is not None:
                    name=self._name(m);pid=m.paper_id; first=self.session.query(sa.func.min(PaperCreatorMention.order_index)).filter_by(paper_id=m.paper_id,creator_type="author").scalar()
                    if first==m.order_index:role=max(role,90)
            out.append({"review_item_id":r.review_item_id,"queue_type":r.queue_type,"subject_type":r.subject_type,"subject_id":r.subject_id,
                        "candidate_id":r.candidate_id,"reason_code":r.reason_code,"stored_priority":r.priority,"effective_priority":max(int(r.priority),role),"source_name":name,"paper_id":pid})
        out.sort(key=lambda z:(-z["effective_priority"],z["review_item_id"]));return out[:min(max(1,limit),500)]

    def search(self,q:str,*,limit:int=20)->dict[str,Any]:
        q=q.strip();return {"query":q,"papers":[] if not q else self.list_papers(q=q,limit=limit)["items"],"authors":[] if not q else self.list_authors(q=q,limit=limit)["items"]}

    def get_pdf_path(self,paper_id:int)->Path:
        rows=(self.session.query(PaperDocument).filter(PaperDocument.paper_id==paper_id,PaperDocument.present_in_last_scan.is_(True),
              PaperDocument.availability_status=="PDF_AVAILABLE",PaperDocument.local_path.is_not(None)).order_by(PaperDocument.document_id).all())
        for r in rows:
            p=Path(r.local_path)
            if p.is_file():return p
        raise PdfUnavailableError(f"paper {paper_id} has no available local PDF")
