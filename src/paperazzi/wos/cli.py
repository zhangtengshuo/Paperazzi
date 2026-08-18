"""Command-line interface for the independent WoS background corpus."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .read import search_records
from .store import WosCorpusStore

DEFAULT_WOS_DB = Path("data/wos.sqlite3")


def _db_path(value: str | None) -> Path:
    return Path(value or os.environ.get("PAPERAZZI_WOS_DB", DEFAULT_WOS_DB))


def _cr_gaps(store: WosCorpusStore, limit: int) -> list[dict[str, object]]:
    with store.connect() as con:
        rows = con.execute(
            """SELECT ut,doi,title,source_title,publication_year,cr_status,best_cr_count,
                      reported_reference_count,last_cr_batch_id,last_imported_at
               FROM wos_records
               WHERE cr_status NOT IN ('COMPLETE','COMPLETE_ZERO')
               ORDER BY
                 CASE WHEN reported_reference_count IS NOT NULL
                      THEN max(reported_reference_count-best_cr_count,0) ELSE 0 END DESC,
                 reported_reference_count DESC,title,ut
               LIMIT ?""",
            (max(1, min(limit, 5000)),),
        ).fetchall()
        return [dict(row) for row in rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperazzi-wos", description="Manage the local WoS background corpus"
    )
    parser.add_argument(
        "--db", help="WoS SQLite path (default: PAPERAZZI_WOS_DB or data/wos.sqlite3)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize or migrate the independent WoS database")
    p_import = sub.add_parser("import", help="Import/merge tagged Plain Text Full Record exports")
    p_import.add_argument("files", nargs="+")
    p_import.add_argument("--label")
    p_import.add_argument("--search-note")
    sub.add_parser("stats", help="Show corpus and cited-reference completeness statistics")
    p_search = sub.add_parser(
        "search", help="Search title, DOI, UT, author, identifier, keyword, institution and funding"
    )
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    p_frontier = sub.add_parser("frontier", help="Rank unresolved cited DOIs for corpus expansion")
    p_frontier.add_argument("--limit", type=int, default=100)
    p_gaps = sub.add_parser(
        "cr-gaps",
        help="List WoS records whose local cited-reference payload is missing, partial, or unverified",
    )
    p_gaps.add_argument("--limit", type=int, default=200)
    p_obs = sub.add_parser("observations", help="Show import observations for one WoS UT")
    p_obs.add_argument("ut")
    p_obs.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = WosCorpusStore(_db_path(args.db))
    if args.command == "init":
        store.initialize()
        payload = {"status": "OK", "database": str(store.path)}
    elif args.command == "import":
        payload = {
            "database": str(store.path),
            "imports": [
                store.import_file(p, label=args.label, search_note=args.search_note)
                for p in args.files
            ],
            "stats": store.stats(),
        }
    elif not store.path.is_file():
        payload = {
            "available": False,
            "database": str(store.path),
            "message": "Local WoS corpus does not exist yet; this is non-blocking. Import a WoS Plain Text export first.",
        }
    else:
        # Existing independent WoS DBs are migrated in place before any v3 read command.
        store.initialize()
        if args.command == "stats":
            payload = {"available": True, "database": str(store.path), **store.stats()}
        elif args.command == "search":
            payload = search_records(store, args.query, limit=args.limit)
        elif args.command == "frontier":
            payload = store.citation_frontier(limit=args.limit)
        elif args.command == "cr-gaps":
            payload = {
                "available": True,
                "database": str(store.path),
                "items": _cr_gaps(store, args.limit),
            }
        elif args.command == "observations":
            record = store.get_record(args.ut)
            payload = {
                "available": True,
                "database": str(store.path),
                "ut": args.ut,
                "record": None if record is None else {
                    "title": record.get("title"),
                    "cr_status": record.get("cr_status"),
                    "reference_count": record.get("reference_count"),
                    "reported_reference_count": record.get("reported_reference_count"),
                },
                "items": store.list_observations(args.ut, limit=args.limit) if record else [],
            }
        else:
            raise AssertionError(args.command)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
