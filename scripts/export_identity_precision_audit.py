#!/usr/bin/env python3
"""Export a deterministic stratified identity precision-audit sample.

Read-only with respect to Paperazzi semantic data: it writes only a JSON audit package.
"""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
import sqlalchemy as sa

REPO_ROOT=Path(__file__).resolve().parents[1]; SRC=REPO_ROOT/"src"
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.models import Paper, PaperCreatorMention  # noqa:E402
from paperazzi.identity.models import Author, AuthorIdentityMembership, AuthorNameVariant, Authorship  # noqa:E402


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--db-path",type=Path,default=REPO_ROOT/"data"/"phase4-validation"/"paperazzi.sqlite3"); p.add_argument("--output",type=Path,default=REPO_ROOT/"data"/"phase4-validation"/"identity_precision_audit.json"); p.add_argument("--count",type=int,default=50); p.add_argument("--seed",type=int,default=20260817); a=p.parse_args()
    engine=create_paperazzi_engine(a.db_path); sf=sa.orm.sessionmaker(bind=engine); rng=random.Random(a.seed)
    with sf() as s:
        rows=(s.query(AuthorIdentityMembership,PaperCreatorMention,Author,Paper).join(PaperCreatorMention,PaperCreatorMention.creator_mention_id==AuthorIdentityMembership.creator_mention_id).join(Author,Author.author_id==AuthorIdentityMembership.author_id).join(Paper,Paper.paper_id==PaperCreatorMention.paper_id).filter(AuthorIdentityMembership.status=="ACCEPTED",AuthorIdentityMembership.reason_code=="STRONG_IMMUTABLE_SOURCE_IDENTITY_EVIDENCE").all())
        samples=[]
        for mem,m,author,paper in rows:
            same_name=s.query(Author).filter(Author.status=="ACTIVE",Author.normalized_name==author.normalized_name).count() if author.normalized_name else 0
            degree=s.query(Authorship).filter_by(author_id=author.author_id,status="ACTIVE").count()
            auth=s.query(Authorship).filter_by(creator_mention_id=m.creator_mention_id,status="ACTIVE").one_or_none()
            cats=[]
            if mem.score is not None and mem.score < 0.95: cats.append("THRESHOLD_EDGE")
            if same_name>1: cats.append("SAME_NORMALIZED_NAME_MULTIPLE_IDENTITIES")
            if degree>=5: cats.append("HIGH_PUBLICATION_DEGREE")
            if auth is not None and auth.is_first_author: cats.append("FIRST_AUTHOR")
            if not cats: cats=["GENERAL"]
            samples.append({"membership_id":mem.membership_id,"creator_mention_id":m.creator_mention_id,"author_id":author.author_id,"source_name":m.display_name or " ".join(x for x in (m.first_name,m.last_name) if x),"preferred_name":author.preferred_name,"paper_id":paper.paper_id,"paper_title":paper.title,"score":mem.score,"score_components":json.loads(mem.score_components_json or "{}"),"risk_categories":cats,"audit_decision":None,"audit_notes":None})
        chosen=[]; used=set()
        for cat in ["SAME_NORMALIZED_NAME_MULTIPLE_IDENTITIES","THRESHOLD_EDGE","FIRST_AUTHOR","HIGH_PUBLICATION_DEGREE","GENERAL"]:
            pool=[x for x in samples if cat in x["risk_categories"] and x["membership_id"] not in used]; rng.shuffle(pool)
            quota=max(1,a.count//5)
            for x in pool[:quota]: chosen.append(x); used.add(x["membership_id"])
        remaining=[x for x in samples if x["membership_id"] not in used]; rng.shuffle(remaining); chosen.extend(remaining[:max(0,a.count-len(chosen))]); chosen=chosen[:a.count]
    package={"schema":"paperazzi.identity_precision_audit.v1","source_db":str(a.db_path),"sample_count":len(chosen),"instructions":"For each row set audit_decision to CORRECT, FALSE_MERGE, or UNCERTAIN after checking independent evidence. Do not change resolver thresholds from coverage pressure alone.","items":chosen}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding="utf-8"); print(a.output); engine.dispose(); return 0

if __name__=="__main__": raise SystemExit(main())
