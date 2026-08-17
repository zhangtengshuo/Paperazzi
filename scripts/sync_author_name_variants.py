#!/usr/bin/env python3
"""Backfill all accepted source author spellings into AuthorNameVariant."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import sqlalchemy as sa
REPO_ROOT=Path(__file__).resolve().parents[1]; SRC=REPO_ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.identity.manual_review import sync_author_name_variants  # noqa:E402

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--db-path',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    if not args.db_path.is_file(): print(json.dumps({'error':'database not found'}));return 2
    engine=create_paperazzi_engine(args.db_path);sf=sa.orm.sessionmaker(bind=engine)
    try:
        with sf() as session:
            if not args.apply:
                accepted=session.execute(sa.text("SELECT COUNT(*) FROM author_identity_memberships WHERE status='ACCEPTED'" )).scalar_one()
                current=session.execute(sa.text("SELECT COUNT(*) FROM author_name_variants WHERE variant_type='SOURCE'" )).scalar_one()
                print(json.dumps({'dry_run':True,'accepted_memberships':accepted,'current_source_variants':current},indent=2));return 0
            result=sync_author_name_variants(session);session.commit();print(json.dumps({'applied':True,**result},indent=2));return 0
    finally: engine.dispose()
if __name__=='__main__': raise SystemExit(main())
