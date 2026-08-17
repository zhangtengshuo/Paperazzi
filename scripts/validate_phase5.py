#!/usr/bin/env python3
"""Read-only Phase 5 smoke validation against a real Paperazzi database."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import sqlalchemy as sa

REPO_ROOT=Path(__file__).resolve().parents[1]; SRC=REPO_ROOT/"src"
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from fastapi.testclient import TestClient  # noqa:E402
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.models import Paper, PaperCreatorMention, PaperDocument  # noqa:E402
from paperazzi.identity.models import Author  # noqa:E402
from paperazzi.web.api import create_app  # noqa:E402
from paperazzi.web.queries import PaperazziQueryService  # noqa:E402

DEFAULT_DB=REPO_ROOT/"data"/"phase4-validation"/"paperazzi.sqlite3"
DEFAULT_REPORT=REPO_ROOT/"data"/"phase5-validation"/"phase5_report.json"

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--db-path",type=Path,default=DEFAULT_DB);p.add_argument("--report-path",type=Path,default=DEFAULT_REPORT);p.add_argument("--sample-papers",type=int,default=200);a=p.parse_args()
    if not a.db_path.is_file(): raise FileNotFoundError(a.db_path)
    engine=create_paperazzi_engine(a.db_path); sf=sa.orm.sessionmaker(bind=engine)
    with sf() as s:
        service=PaperazziQueryService(s)
        paper_count=s.query(Paper).filter(Paper.active_in_zotero.is_(True)).count(); author_count=s.query(Author).filter_by(status="ACTIVE").count()
        papers=s.query(Paper).filter(Paper.active_in_zotero.is_(True)).order_by(Paper.paper_id).limit(max(1,a.sample_papers)).all()
        mismatches=[]; unresolved_visible=0
        for paper in papers:
            expected=s.query(PaperCreatorMention).filter_by(paper_id=paper.paper_id,creator_type="author").count(); detail=service.get_paper(paper.paper_id); observed=len(detail["authors"])
            if expected!=observed: mismatches.append({"paper_id":paper.paper_id,"expected":expected,"observed":observed})
            unresolved_visible += sum(x["identity_status"]=="UNRESOLVED" for x in detail["authors"])
        search_ok=True
        first_named=s.query(Author).filter(Author.status=="ACTIVE",Author.preferred_name.is_not(None)).first()
        if first_named is not None:
            token=(first_named.preferred_name or "").split()[0]
            search_ok=bool(token and service.search(token,limit=10)["authors"])
        available_pdf_rows=s.query(PaperDocument).filter_by(availability_status="PDF_AVAILABLE",present_in_last_scan=True).count()
        reachable_pdf=0
        for (paper_id,) in s.query(PaperDocument.paper_id).filter_by(availability_status="PDF_AVAILABLE",present_in_last_scan=True).distinct().limit(20).all():
            try: service.get_pdf_path(paper_id); reachable_pdf+=1
            except Exception: pass
    client=TestClient(create_app(a.db_path)); http={"home":client.get("/").status_code,"health":client.get("/health").status_code,"papers":client.get("/api/papers",params={"limit":5}).status_code,"authors":client.get("/api/authors",params={"limit":5}).status_code,"search":client.get("/api/search",params={"q":"test","limit":5}).status_code}
    passed=paper_count>0 and author_count>0 and not mismatches and search_ok and all(code==200 for code in http.values())
    report={"phase":"PHASE_5","status":"PASS" if passed else "FAIL","database":str(a.db_path),"paper_count":paper_count,"active_canonical_authors":author_count,"sampled_papers":len(papers),"source_author_projection_mismatches":mismatches,"unresolved_source_authors_visible_in_sample":unresolved_visible,"search_smoke_passed":search_ok,"pdf_available_rows":available_pdf_rows,"reachable_pdf_papers_in_first_20":reachable_pdf,"http_status":http}
    a.report_path.parent.mkdir(parents=True,exist_ok=True);a.report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=False,indent=2));engine.dispose();return 0 if passed else 2

if __name__=="__main__": raise SystemExit(main())
