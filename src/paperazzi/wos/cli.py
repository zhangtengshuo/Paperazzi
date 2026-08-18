"""Command-line interface for the independent WoS background corpus."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .store import WosCorpusStore

DEFAULT_WOS_DB = Path("data/wos.sqlite3")


def _db_path(value: str | None) -> Path:
    return Path(value or os.environ.get("PAPERAZZI_WOS_DB", DEFAULT_WOS_DB))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperazzi-wos",description="Manage the local WoS background corpus")
    parser.add_argument("--db",help="WoS SQLite path (default: PAPERAZZI_WOS_DB or data/wos.sqlite3)")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("init",help="Initialize the independent WoS database")
    p_import=sub.add_parser("import",help="Import tagged Plain Text Full Record exports")
    p_import.add_argument("files",nargs="+"); p_import.add_argument("--label"); p_import.add_argument("--search-note")
    sub.add_parser("stats",help="Show corpus statistics")
    p_search=sub.add_parser("search",help="Search local WoS records"); p_search.add_argument("query"); p_search.add_argument("--limit",type=int,default=20)
    p_frontier=sub.add_parser("frontier",help="Rank unresolved cited DOIs for corpus expansion"); p_frontier.add_argument("--limit",type=int,default=100)
    return parser


def main(argv: Sequence[str]|None=None)->int:
    args=build_parser().parse_args(argv); store=WosCorpusStore(_db_path(args.db))
    if args.command=="init":
        store.initialize(); payload={"status":"OK","database":str(store.path)}
    elif args.command=="import":
        payload={"database":str(store.path),"imports":[store.import_file(p,label=args.label,search_note=args.search_note) for p in args.files],"stats":store.stats()}
    elif args.command=="stats": payload={"database":str(store.path),**store.stats()}
    elif args.command=="search": payload=store.search(args.query,limit=args.limit)
    elif args.command=="frontier": payload=store.citation_frontier(limit=args.limit)
    else: raise AssertionError(args.command)
    print(json.dumps(payload,ensure_ascii=False,indent=2)); return 0


if __name__=="__main__": raise SystemExit(main())
