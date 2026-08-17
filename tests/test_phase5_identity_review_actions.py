"""Regression tests for source-name retention and interactive identity review."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import httpx
import sqlalchemy as sa

REPO_ROOT=Path(__file__).resolve().parents[1];SRC=REPO_ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))

from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.models import Paper, PaperCreatorMention  # noqa:E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa:E402
from paperazzi.identity.models import Author, AuthorIdentityDecision, AuthorNameVariant, Authorship, ResolutionReviewQueue  # noqa:E402
from paperazzi.identity.service import bootstrap_author_identities  # noqa:E402
from paperazzi.identity.manual_review import (  # noqa:E402
    identity_review_detail,
    link_review_mention,
    merge_identity_review_pair,
    refresh_similar_identity_reviews,
    sync_author_name_variants,
)
from paperazzi.ingest.models import CanonicalCreator, CanonicalZoteroItem  # noqa:E402
from paperazzi.web.api import create_app  # noqa:E402
from paperazzi.web.ui import APP_HTML  # noqa:E402


def alembic(*args:str,db_path:Path):
    env=dict(os.environ);env['PAPERAZZI_DB_URL']=f'sqlite:///{db_path}'
    return subprocess.run([sys.executable,'-m','alembic',*args],cwd=REPO_ROOT,env=env,capture_output=True,text=True)

def item(key,item_id,title,first,last,creator_id):
    return CanonicalZoteroItem(library_id=1,item_id=item_id,item_key=key,item_type='journalArticle',zotero_version=1,synced=1,date_added='2026-01-01',date_modified='2026-01-01',client_date_modified='2026-01-01',deleted=False,fields={'title':title,'date':'2026'},creators=(CanonicalCreator(creator_id=creator_id,creator_type='author',order_index=0,first_name=first,last_name=last),),collections=(),tags=(),attachments=())

class IdentityReviewActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'identity.sqlite3'
        proc=alembic('upgrade','head',db_path=self.db);self.assertEqual(proc.returncode,0,proc.stderr[-1500:])
        self.engine=create_paperazzi_engine(self.db);self.sf=sa.orm.sessionmaker(bind=self.engine)
        scan=persist_zotero_scan(self.sf,[
            item('A',1,'Full spelling','Tengshuo','Zhang',10),
            item('B',2,'Hyphen spelling','Teng-Shuo','Zhang',20),
            item('C',3,'Abbreviated spelling','T','Zhang',30),
            item('D',4,'Alex one','Alex','Wang',40),
            item('E',5,'Alex two','Alex','Wang',50),
        ],{'run_token':'identity-ui','source_db_path':'/tmp/fake'})
        self.assertEqual(scan.status,'COMPLETED')
        with self.sf() as s:
            bootstrap_author_identities(s);s.commit()
    def tearDown(self):self.engine.dispose();self.tmp.cleanup()

    def test_sync_records_all_accepted_source_spellings(self):
        with self.sf() as s:
            result=sync_author_name_variants(s);s.commit()
            self.assertGreaterEqual(result['accepted_mentions_seen'],3)
            raw={r.raw_name for r in s.query(AuthorNameVariant).all()}
            self.assertIn('Tengshuo Zhang',raw);self.assertIn('Teng-Shuo Zhang',raw);self.assertIn('T Zhang',raw)

    def test_hyphen_variant_is_suggested_and_manual_merge_preserves_both_names(self):
        with self.sf() as s:
            sync_author_name_variants(s)
            refresh=refresh_similar_identity_reviews(s,minimum_score=.5,max_new_reviews=50)
            self.assertGreater(refresh['reviews_created_or_updated'],0)
            full=s.query(Author).filter_by(preferred_name='Tengshuo Zhang',status='ACTIVE').one()
            hyphen=s.query(Author).filter_by(preferred_name='Teng-Shuo Zhang',status='ACTIVE').one()
            review=(s.query(ResolutionReviewQueue).filter(ResolutionReviewQueue.status=='OPEN',ResolutionReviewQueue.subject_type=='author',ResolutionReviewQueue.subject_id==full.author_id,ResolutionReviewQueue.candidate_id==hyphen.author_id).one_or_none()
                    or s.query(ResolutionReviewQueue).filter(ResolutionReviewQueue.status=='OPEN',ResolutionReviewQueue.subject_type=='author',ResolutionReviewQueue.subject_id==hyphen.author_id,ResolutionReviewQueue.candidate_id==full.author_id).one())
            source,target=(hyphen.author_id,full.author_id)
            merge_identity_review_pair(s,source,target,review_item_id=review.review_item_id,notes='same person verified');s.commit()
            self.assertEqual(s.get(Author,source).status,'MERGED')
            names={v.raw_name for v in s.query(AuthorNameVariant).filter_by(author_id=target).all()}
            self.assertIn('Tengshuo Zhang',names);self.assertIn('Teng-Shuo Zhang',names)
            self.assertEqual(s.query(Authorship).filter_by(author_id=target,status='ACTIVE').count(),2)
            self.assertIsNotNone(s.query(AuthorIdentityDecision).filter_by(operation='MERGE_IDENTITY',source_author_id=source,target_author_id=target).first())

    def test_unresolved_same_name_can_be_compared_and_manually_linked(self):
        with self.sf() as s:
            alex2=(s.query(PaperCreatorMention).join(Paper,Paper.paper_id==PaperCreatorMention.paper_id).filter(Paper.title=='Alex two').one())
            review=s.query(ResolutionReviewQueue).filter_by(queue_type='AMBIGUOUS_AUTHOR_IDENTITY',subject_type='creator_mention',subject_id=str(alex2.creator_mention_id),status='OPEN').one()
            detail=identity_review_detail(s,review.review_item_id)
            self.assertEqual(detail['source_mention']['source_name'],'Alex Wang')
            self.assertGreaterEqual(len(detail['candidates']),1)
            target=detail['candidates'][0]['author_id']
            link_review_mention(s,review.review_item_id,target,notes='manual compare');s.commit()
            self.assertEqual(s.get(ResolutionReviewQueue,review.review_item_id).status,'RESOLVED')
            self.assertEqual(s.query(Authorship).filter_by(creator_mention_id=alex2.creator_mention_id,status='ACTIVE').one().author_id,target)

    def test_api_exposes_review_detail_and_write_actions(self):
        async def run():
            transport=httpx.ASGITransport(app=create_app(self.db))
            async with httpx.AsyncClient(transport=transport,base_url='http://test',trust_env=False) as client:
                r=await client.post('/api/reviews/identity/sync-name-variants');self.assertEqual(r.status_code,200,r.text)
                r=await client.post('/api/reviews/identity/refresh-similar');self.assertEqual(r.status_code,200,r.text)
                rows=(await client.get('/api/reviews/identity?limit=100')).json();self.assertTrue(rows)
                detail=await client.get(f"/api/reviews/identity/{rows[0]['review_item_id']}");self.assertEqual(detail.status_code,200,detail.text)
        asyncio.run(run())

    def test_ui_explains_identity_and_has_persistent_jump_pagination(self):
        self.assertIn('IDENTITY UNRESOLVED',APP_HTML)
        self.assertIn('Paperazzi ID',APP_HTML)
        self.assertIn('Refresh similar names',APP_HTML)
        self.assertIn('jumpPage',APP_HTML)
        self.assertIn('position:sticky',APP_HTML)

if __name__=='__main__':unittest.main()
