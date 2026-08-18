"""Persistence for recomputable Graph Analytics outputs.

Derived analytics live in their own SQLite database.  No source fact is written back to
``wos.sqlite3`` or ``paperazzi.sqlite3``.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
import uuid

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS analytics_meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_runs(
    analysis_run_id TEXT PRIMARY KEY,
    analysis_type TEXT NOT NULL,
    input_snapshot_hash TEXT NOT NULL,
    corpus_definition_json TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    code_version TEXT NOT NULL,
    input_quality_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_type_status
    ON analysis_runs(analysis_type,status,completed_at);
CREATE TABLE IF NOT EXISTS analysis_nodes(
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
    node_type TEXT NOT NULL,
    node_key TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    PRIMARY KEY(analysis_run_id,node_type,node_key)
);
CREATE INDEX IF NOT EXISTS ix_analysis_nodes_run_type
    ON analysis_nodes(analysis_run_id,node_type);
CREATE TABLE IF NOT EXISTS analysis_edges(
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    predicate TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_key TEXT NOT NULL,
    weight REAL,
    components_json TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    PRIMARY KEY(analysis_run_id,source_type,source_key,predicate,target_type,target_key)
);
CREATE INDEX IF NOT EXISTS ix_analysis_edges_source
    ON analysis_edges(analysis_run_id,predicate,source_key);
CREATE INDEX IF NOT EXISTS ix_analysis_edges_target
    ON analysis_edges(analysis_run_id,predicate,target_key);
CREATE TABLE IF NOT EXISTS analysis_clusters(
    analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id) ON DELETE CASCADE,
    cluster_id TEXT NOT NULL,
    label TEXT,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY(analysis_run_id,cluster_id)
);
CREATE TABLE IF NOT EXISTS analysis_cluster_members(
    analysis_run_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    node_key TEXT NOT NULL,
    membership_weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY(analysis_run_id,cluster_id,node_type,node_key),
    FOREIGN KEY(analysis_run_id,cluster_id)
      REFERENCES analysis_clusters(analysis_run_id,cluster_id) ON DELETE CASCADE
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class AnalyticsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(self.path)
        else:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=5000")
        if write:
            con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            if write:
                con.commit()
        except Exception:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect(write=True) as con:
            con.executescript(SCHEMA_SQL)
            con.execute(
                "INSERT INTO analytics_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def begin_run(
        self,
        *,
        analysis_type: str,
        input_snapshot_hash: str,
        corpus_definition: dict[str, Any],
        algorithm: str,
        parameters: dict[str, Any],
        code_version: str,
        input_quality: dict[str, Any],
    ) -> str:
        self.initialize()
        run_id = uuid.uuid4().hex
        with self.connect(write=True) as con:
            con.execute(
                """INSERT INTO analysis_runs(
                   analysis_run_id,analysis_type,input_snapshot_hash,corpus_definition_json,
                   algorithm,parameters_json,code_version,input_quality_json,started_at,status)
                   VALUES(?,?,?,?,?,?,?,?,?,'RUNNING')""",
                (
                    run_id,
                    analysis_type,
                    input_snapshot_hash,
                    _json(corpus_definition),
                    algorithm,
                    _json(parameters),
                    code_version,
                    _json(input_quality),
                    _now(),
                ),
            )
        return run_id

    def fail_run(self, run_id: str, exc: BaseException) -> None:
        with self.connect(write=True) as con:
            con.execute(
                "UPDATE analysis_runs SET status='FAILED',completed_at=?,error=? WHERE analysis_run_id=?",
                (_now(), f"{type(exc).__name__}: {exc}", run_id),
            )

    def complete_run(self, run_id: str) -> None:
        with self.connect(write=True) as con:
            con.execute(
                "UPDATE analysis_runs SET status='COMPLETED',completed_at=? WHERE analysis_run_id=?",
                (_now(), run_id),
            )

    def write_nodes(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.connect(write=True) as con:
            con.executemany(
                """INSERT OR REPLACE INTO analysis_nodes(
                   analysis_run_id,node_type,node_key,attributes_json) VALUES(?,?,?,?)""",
                [
                    (
                        run_id,
                        str(row.get("node_type", "PAPER")),
                        str(row["node_key"]),
                        _json(row.get("attributes", {})),
                    )
                    for row in rows
                ],
            )

    def write_edges(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.connect(write=True) as con:
            con.executemany(
                """INSERT OR REPLACE INTO analysis_edges(
                   analysis_run_id,source_type,source_key,predicate,target_type,target_key,
                   weight,components_json,quality_status) VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        run_id,
                        str(row.get("source_type", "PAPER")),
                        str(row["source_key"]),
                        str(row["predicate"]),
                        str(row.get("target_type", "PAPER")),
                        str(row["target_key"]),
                        float(row["weight"]) if row.get("weight") is not None else None,
                        _json(row.get("components", {})),
                        str(row.get("quality_status", "DERIVED")),
                    )
                    for row in rows
                ],
            )

    def write_clusters(
        self,
        run_id: str,
        clusters: list[dict[str, Any]],
        members: list[dict[str, Any]],
    ) -> None:
        with self.connect(write=True) as con:
            if clusters:
                con.executemany(
                    """INSERT OR REPLACE INTO analysis_clusters(
                       analysis_run_id,cluster_id,label,metrics_json) VALUES(?,?,?,?)""",
                    [
                        (
                            run_id,
                            str(row["cluster_id"]),
                            row.get("label"),
                            _json(row.get("metrics", {})),
                        )
                        for row in clusters
                    ],
                )
            if members:
                con.executemany(
                    """INSERT OR REPLACE INTO analysis_cluster_members(
                       analysis_run_id,cluster_id,node_type,node_key,membership_weight)
                       VALUES(?,?,?,?,?)""",
                    [
                        (
                            run_id,
                            str(row["cluster_id"]),
                            str(row.get("node_type", "PAPER")),
                            str(row["node_key"]),
                            float(row.get("membership_weight", 1.0)),
                        )
                        for row in members
                    ],
                )

    def latest_run(self, analysis_type: str = "GRAPH_ANALYTICS_V1") -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        with self.connect() as con:
            row = con.execute(
                """SELECT * FROM analysis_runs
                   WHERE analysis_type=? AND status='COMPLETED'
                   ORDER BY completed_at DESC,started_at DESC LIMIT 1""",
                (analysis_type,),
            ).fetchone()
            return self._run_dict(row) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM analysis_runs WHERE analysis_run_id=?", (run_id,)).fetchone()
            return self._run_dict(row) if row else None

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["corpus_definition"] = _decode(result.pop("corpus_definition_json"), {})
        result["parameters"] = _decode(result.pop("parameters_json"), {})
        result["input_quality"] = _decode(result.pop("input_quality_json"), {})
        return result

    def node(self, run_id: str, node_key: str, node_type: str = "PAPER") -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                """SELECT node_type,node_key,attributes_json FROM analysis_nodes
                   WHERE analysis_run_id=? AND node_type=? AND node_key=?""",
                (run_id, node_type, node_key),
            ).fetchone()
            if row is None:
                return None
            return {
                "node_type": row["node_type"],
                "node_key": row["node_key"],
                "attributes": _decode(row["attributes_json"], {}),
            }

    def top_nodes(
        self,
        run_id: str,
        metric: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT node_key,attributes_json FROM analysis_nodes WHERE analysis_run_id=? AND node_type='PAPER'",
                (run_id,),
            ).fetchall()
        decoded = [
            {"node_key": row["node_key"], "attributes": _decode(row["attributes_json"], {})}
            for row in rows
        ]
        decoded.sort(
            key=lambda row: (
                -float(row["attributes"].get("metrics", {}).get(metric, 0.0) or 0.0),
                row["node_key"],
            )
        )
        return decoded[: max(1, min(limit, 500))]

    def edges_for_node(
        self,
        run_id: str,
        node_key: str,
        *,
        predicates: tuple[str, ...] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["analysis_run_id=?", "(source_key=? OR target_key=?)"]
        params: list[Any] = [run_id, node_key, node_key]
        if predicates:
            placeholders = ",".join("?" for _ in predicates)
            clauses.append(f"predicate IN ({placeholders})")
            params.extend(predicates)
        params.append(max(1, min(limit, 5000)))
        with self.connect() as con:
            rows = con.execute(
                f"""SELECT * FROM analysis_edges WHERE {' AND '.join(clauses)}
                    ORDER BY coalesce(weight,0) DESC,predicate,source_key,target_key LIMIT ?""",
                params,
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["components"] = _decode(item.pop("components_json"), {})
            result.append(item)
        return result

    def edges(
        self,
        run_id: str,
        predicate: str,
        *,
        limit: int = 100000,
    ) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """SELECT * FROM analysis_edges WHERE analysis_run_id=? AND predicate=?
                   ORDER BY coalesce(weight,0) DESC,source_key,target_key LIMIT ?""",
                (run_id, predicate, max(1, min(limit, 500000))),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["components"] = _decode(item.pop("components_json"), {})
            result.append(item)
        return result

    def clusters(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            clusters = [dict(row) for row in con.execute(
                "SELECT * FROM analysis_clusters WHERE analysis_run_id=? ORDER BY cluster_id", (run_id,)
            ).fetchall()]
            members = [dict(row) for row in con.execute(
                """SELECT * FROM analysis_cluster_members WHERE analysis_run_id=?
                   ORDER BY cluster_id,node_key""",
                (run_id,),
            ).fetchall()]
        members_by_cluster: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            members_by_cluster.setdefault(str(member["cluster_id"]), []).append(member)
        result = []
        for cluster in clusters:
            result.append(
                {
                    "analysis_run_id": run_id,
                    "cluster_id": cluster["cluster_id"],
                    "label": cluster["label"],
                    "metrics": _decode(cluster["metrics_json"], {}),
                    "members": members_by_cluster.get(str(cluster["cluster_id"]), []),
                }
            )
        return result

    def stats(self, run_id: str | None = None) -> dict[str, Any]:
        run = self.get_run(run_id) if run_id else self.latest_run()
        if run is None:
            return {"available": self.path.is_file(), "latest_run": None}
        with self.connect() as con:
            node_count = int(con.execute(
                "SELECT count(*) FROM analysis_nodes WHERE analysis_run_id=?", (run["analysis_run_id"],)
            ).fetchone()[0])
            edge_counts = {
                str(row[0]): int(row[1])
                for row in con.execute(
                    """SELECT predicate,count(*) FROM analysis_edges WHERE analysis_run_id=?
                       GROUP BY predicate ORDER BY predicate""",
                    (run["analysis_run_id"],),
                ).fetchall()
            }
            cluster_count = int(con.execute(
                "SELECT count(*) FROM analysis_clusters WHERE analysis_run_id=?", (run["analysis_run_id"],)
            ).fetchone()[0])
        return {
            "available": True,
            "latest_run": run,
            "nodes": node_count,
            "edges_by_predicate": edge_counts,
            "clusters": cluster_count,
        }


__all__ = ["AnalyticsStore", "SCHEMA_VERSION"]
