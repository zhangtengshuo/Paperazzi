"""Match Paperazzi papers to an independently imported WoS background corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sqlalchemy as sa

from paperazzi.database.engine import create_paperazzi_engine
from paperazzi.wos.integration import match_all_papers


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--paperazzi-db",default="data/paperazzi.sqlite3")
    parser.add_argument("--wos-db",default="data/wos.sqlite3")
    parser.add_argument("--apply",action="store_true",help="persist accepted exact links; default is dry run")
    parser.add_argument("--unmatched-output",help="optional JSONL output for non-matched/ambiguous papers")
    args=parser.parse_args()
    engine=create_paperazzi_engine(Path(args.paperazzi_db)); factory=sa.orm.sessionmaker(bind=engine)
    try:
        with factory() as session:
            result=match_all_papers(session,Path(args.wos_db),apply=args.apply)
            if args.apply:session.commit()
            if args.unmatched_output:
                rows=[d for d in result["decisions"] if d["status"]!="WOS_MATCHED"]
                Path(args.unmatched_output).write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
            print(json.dumps({k:v for k,v in result.items() if k!="decisions"},ensure_ascii=False,indent=2))
    finally:engine.dispose()
    return 0


if __name__=="__main__":raise SystemExit(main())
