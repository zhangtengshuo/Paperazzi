"""Regression test for persistent canonical different-person review decisions."""
from __future__ import annotations
import os,subprocess,sys,tempfile,unittest
from pathlib import Path
import sqlalchemy as sa
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa:E402
from paperazzi.identity.models import Author,AuthorIdentityDecision,ResolutionReviewQueue  # noqa:E402
from paperazzi.identity.pair_decisions import mark_canonical_authors_not_same  # noqa:E402
from paperazzi.identity.service import bootstrap_author_identities  # noqa:E402
from paperazzi.identity.similar_names import refresh_similar_identity_reviews,similar_author_candidates  # noqa:E402
from paperazzi.ingest.models import CanonicalCreator,CanonicalZoteroItem  # noqa:E402

def alembic(*args,db_path):
    env=dict(os.environ);env['PAPERAZZI_DB_URL']=f'sqlite:///{db_path}'
    return subprocess.run([sys.executable,'-m','alembic',*args],cwd=ROOT,env=env,capture_output=True,text=True)
def item(i,key,first,last):
    return CanonicalZoteroItem(library_id=1,item_id=i,item_key=key,item_type='journalArticle',zotero_version=1,synced=1,date_added='2026-01-01',date_modified='2026-01-01',client_date_modified='2026-01-01',deleted=False,fields={'title':f'Paper {i}','date':'2026'},creators=(CanonicalCreator(creator_id=i,creator_type='author',order_index=0,first_name=first,last_name=last),),collections=(),tags=(),attachments=())

class CanonicalPairDecisionTests(unittest.TestCase):
    def test_different_people_decision_prevents_future_name_suggestion(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'pair.sqlite3';proc=alembic('upgrade','head',db_path=db);self.assertEqual(proc.returncode,0,proc.stderr[-1200:])
            engine=create_paperazzi_engine(db);sf=sa.orm.sessionmaker(bind=engine)
            self.assertEqual(persist_zotero_scan(sf,[item(1,'A','Tengshuo','Zhang'),item(2,'B','Teng-Shuo','Zhang')],{'run_token':'pair','source_db_path':'/tmp/fake'}).status,'COMPLETED')
            with sf() as s:
                bootstrap_author_identities(s);refresh_similar_identity_reviews(s);s.commit()
                authors=s.query(Author).filter(Author.status=='ACTIVE').order_by(Author.author_id).all();self.assertEqual(len(authors),2)
                left,right=authors[0],authors[1]
                review=s.query(ResolutionReviewQueue).filter_by(queue_type='SIMILAR_AUTHOR_IDENTITY',subject_type='author',subject_id=left.author_id,status='OPEN').one_or_none()
                if review is None:
                    review=s.query(ResolutionReviewQueue).filter_by(queue_type='SIMILAR_AUTHOR_IDENTITY',subject_type='author',subject_id=right.author_id,status='OPEN').one()
                mark_canonical_authors_not_same(s,left.author_id,right.author_id,review_item_id=review.review_item_id,notes='verified different');s.commit()
                self.assertEqual(s.get(ResolutionReviewQueue,review.review_item_id).status,'RESOLVED')
                decision=s.query(AuthorIdentityDecision).filter_by(operation='NOT_SAME_PERSON',creator_mention_id=None).one();self.assertEqual({decision.source_author_id,decision.target_author_id},{left.author_id,right.author_id})
                self.assertEqual(similar_author_candidates(s,left.author_id),[])
                before=s.query(ResolutionReviewQueue).filter_by(queue_type='SIMILAR_AUTHOR_IDENTITY',status='OPEN').count()
                refresh_similar_identity_reviews(s);s.flush()
                after=s.query(ResolutionReviewQueue).filter_by(queue_type='SIMILAR_AUTHOR_IDENTITY',status='OPEN').count();self.assertEqual(after,before)
            engine.dispose()

if __name__=='__main__':unittest.main()
