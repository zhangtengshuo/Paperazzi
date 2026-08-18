"""CLI for deterministic Paperazzi Graph Analytics."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .builder import GraphAnalyticsBuilder
from .service import GraphAnalyticsService

DEFAULT_WOS_DB = Path("data/wos.sqlite3")
DEFAULT_ANALYTICS_DB = Path("data/analytics.sqlite3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperazzi-analytics",
        description="Build and query deterministic scholarly graph analytics",
    )
    parser.add_argument("--wos-db", default=os.environ.get("PAPERAZZI_WOS_DB", str(DEFAULT_WOS_DB)))
    parser.add_argument(
        "--analytics-db",
        default=os.environ.get("PAPERAZZI_ANALYTICS_DB", str(DEFAULT_ANALYTICS_DB)),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build a versioned Graph Analytics run")
    p_build.add_argument("--min-shared-references", type=int, default=2)
    p_build.add_argument("--min-co-citation", type=int, default=2)
    p_build.add_argument("--community-min-weight", type=float, default=0.10)

    sub.add_parser("stats", help="Show latest analytics-run statistics")

    p_centrality = sub.add_parser("centrality", help="Rank paper nodes by a structural metric")
    p_centrality.add_argument(
        "--metric",
        choices=["pagerank_local", "betweenness_undirected", "in_degree_local", "out_degree_local_observed"],
        default="pagerank_local",
    )
    p_centrality.add_argument("--limit", type=int, default=30)

    p_related = sub.add_parser("related", help="Explain related papers for a WoS UT")
    p_related.add_argument("ut")
    p_related.add_argument("--limit", type=int, default=30)

    p_neighborhood = sub.add_parser("neighborhood", help="Inspect a paper graph neighborhood")
    p_neighborhood.add_argument("ut")
    p_neighborhood.add_argument("--limit", type=int, default=30)

    p_connector = sub.add_parser("connector", help="Find explainable citation paths between two WoS UTs")
    p_connector.add_argument("source_ut")
    p_connector.add_argument("target_ut")
    p_connector.add_argument("--max-paths", type=int, default=3)
    p_connector.add_argument("--max-hops", type=int, default=8)

    sub.add_parser("communities", help="Show derived paper communities")
    p_rpys = sub.add_parser("rpys", help="Show Reference Publication Year Spectroscopy")
    p_rpys.add_argument("--peaks-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    analytics_path = Path(args.analytics_db)
    if args.command == "build":
        payload = GraphAnalyticsBuilder(args.wos_db, analytics_path).build(
            min_shared_references=max(1, args.min_shared_references),
            min_co_citation=max(1, args.min_co_citation),
            community_min_weight=max(0.0, args.community_min_weight),
        )
    else:
        service = GraphAnalyticsService(analytics_path)
        if args.command == "stats":
            payload = service.stats()
        elif args.command == "centrality":
            payload = service.centrality(metric=args.metric, limit=args.limit)
        elif args.command == "related":
            payload = service.related(args.ut, limit=args.limit)
        elif args.command == "neighborhood":
            payload = service.neighborhood(args.ut, limit=args.limit)
        elif args.command == "connector":
            payload = service.connector(
                args.source_ut,
                args.target_ut,
                max_paths=max(1, args.max_paths),
                max_hops=max(1, args.max_hops),
            )
        elif args.command == "communities":
            payload = service.communities()
        elif args.command == "rpys":
            payload = service.rpys(peaks_only=args.peaks_only)
        else:  # pragma: no cover
            raise AssertionError(args.command)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
