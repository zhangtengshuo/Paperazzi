#!/usr/bin/env python3
"""Queue conservative similar-name canonical identities for manual review."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import sqlalchemy as sa
REPO_ROOT=Path(__file__).resolve().parents[1];SRC=REPO_ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from paperazzi.database.engine import create_paperazzi_engine  # noqa:E402
from paperazzi.identity.similar_names import refresh_similar_identity_reviews  # noqa:E402

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--db-path',type=Path,required=True);p.add_argument('--minimum-score',type=float,default=0.50);p.add_argument('--max-new-reviews',type=int,default=500);p.add_argument('--apply',action='store_true');a=p.parse_args()
    if not a.db_path.is_file():print(json.dumps({'error':'database not found'}));return 2
    engine=create_paperazzi_engine(a.db_path);sf=sa.orm.sessionmaker(bind=engine)
    try:
        with sf() as s:
            if not a.apply:
                result=refresh_similar_identity_reviews(s,minimum_score=a.minimum_score,max_new_reviews=a.max_new_reviews);s.rollback();print(json.dumps({'dry_run':True,**result},indent=2));return 0
            result=refresh_similar_identity_reviews(s,minimum_score=a.minimum_score,max_new_reviews=a.max_new_reviews);s.commit();print(json.dumps({'applied':True,**result},indent=2));return 0
    finally:engine.dispose()
if __name__=='__main__':raise SystemExit(main())
