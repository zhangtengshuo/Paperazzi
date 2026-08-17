"""Regression tests for provenance-bearing author profile evidence."""
from __future__ import annotations
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
import sqlalchemy as sa
REPO_ROOT=Path(__file__).resolve().parents[1];SRC=REPO_ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.database.persistence import persist_zotero_scan  # noqa:E402
from paperazzi.identity.models import Authorship,AuthorshipEvidence  # noqa:E402
from paperazzi.identity.profile_evidence import author_sourced_evidence  # noqa:E402
from paperazzi.identity.service import bootstrap_author_identities  # noqa:E402
from paperazzi.ingest.models import CanonicalCreator,CanonicalZoteroItem  # noqa:E402
from paperazzi.web.ui import APP_HTML  # noqa:E402

def alembic(*args,db_path):
    env=dict(os.environ);env['PAPERAZZI_DB_URL']=f'sqlite:///{db_path}'
    return subprocess.run([sys.executable,'-m','alembic',*args],cwd=REPO_ROOT,env=env,capture_output=True,text=True)

class AuthorProfileEvidenceTests(unittest.TestCase):
    def test_only_current_candidate_or_accepted_evidence_is_exposed(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'e.sqlite3';p=alembic('upgrade','head',db_path=db);self.assertEqual(p.returncode,0,p.stderr[-1200:])
            engine=create_paperazzi_engine(db);sf=sa.orm.sessionmaker(bind=engine)
            item=CanonicalZoteroItem(library_id=1,item_id=1,item_key='A',item_type='journalArticle',zotero_version=1,synced=1,date_added='2026-01-01',date_modified='2026-01-01',client_date_modified='2026-01-01',deleted=False,fields={'title':'Evidence paper','date':'2026'},creators=(CanonicalCreator(creator_id=1,creator_type='author',order_index=0,first_name='Tengshuo',last_name='Zhang'),),collections=(),tags=(),attachments=())
            self.assertEqual(persist_zotero_scan(sf,[item],{'run_token':'evidence','source_db_path':'/tmp/fake'}).status,'COMPLETED')
            with sf() as s:
                bootstrap_author_identities(s);a=s.query(Authorship).one()
                s.add_all([
                    AuthorshipEvidence(authorship_id=a.authorship_id,evidence_type='AFFILIATION',status='CANDIDATE',raw_value='Example University',resolver='test',score=.7),
                    AuthorshipEvidence(authorship_id=a.authorship_id,evidence_type='CORRESPONDING_AUTHOR',status='ACCEPTED',raw_value='Email: author@example.org',resolver='test',score=1.0),
                    AuthorshipEvidence(authorship_id=a.authorship_id,evidence_type='AFFILIATION',status='SUPERSEDED',raw_value='Old Wrong Institute',resolver='test',score=.7),
                ]);s.commit();rows=author_sourced_evidence(s,a.author_id)
                self.assertEqual({r['status'] for r in rows},{'ACCEPTED','CANDIDATE'})
                self.assertNotIn('Old Wrong Institute',{r['raw_value'] for r in rows})
                self.assertTrue(all(r['paper_id'] for r in rows))
            engine.dispose()
    def test_ui_labels_sourced_evidence_as_noncanonical(self):
        self.assertIn('Sourced affiliation / contact evidence',APP_HTML)
        self.assertIn('CANDIDATE evidence is not a verified current affiliation',APP_HTML)

if __name__=='__main__':unittest.main()
