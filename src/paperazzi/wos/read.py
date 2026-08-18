"""Rich read projections over the normalized independent WoS corpus."""
from __future__ import annotations

import re
from typing import Any

from .store import WosCorpusStore

_FUNDING_ITEM_RE = re.compile(r"^(.*?)(?:\s*\[([^\]]+)\])?$")


def parse_funding_items(raw_fu: str | None) -> list[dict[str, Any]]:
    """Conservatively split WoS FU into funder/grant display/search items.

    Raw FU/FX remain authoritative and are always retained. This helper only adds
    a reversible convenience projection; it does not attempt funder identity resolution.
    """
    if not raw_fu:
        return []
    out: list[dict[str, Any]] = []
    for i, chunk in enumerate(x.strip() for x in raw_fu.split(";") if x.strip()):
        match = _FUNDING_ITEM_RE.match(chunk)
        funder = (match.group(1) if match else chunk).strip()
        grants_raw = match.group(2).strip() if match and match.group(2) else None
        grants = [x.strip() for x in grants_raw.split(",") if x.strip()] if grants_raw else []
        out.append({
            "order_index": i,
            "funder": funder,
            "grants": grants,
            "raw_value": chunk,
        })
    return out


def rich_record(store: WosCorpusStore, ut: str) -> dict[str, Any] | None:
    """Return one WoS record with author identifiers/addresses and metric history."""
    record = store.get_record(ut)
    if record is None:
        return None
    with store.connect() as con:
        identifiers_by_author: dict[int, list[dict[str, str]]] = {}
        for row in con.execute(
            "SELECT wos_author_id,namespace,value,raw_value FROM wos_author_identifiers "
            "WHERE ut=? ORDER BY identifier_id", (ut,)
        ).fetchall():
            if row["wos_author_id"] is None:
                continue
            identifiers_by_author.setdefault(int(row["wos_author_id"]), []).append({
                "namespace": row["namespace"],
                "value": row["value"],
                "raw_value": row["raw_value"],
            })

        addresses_by_author: dict[int, list[str]] = {}
        for row in con.execute(
            "SELECT aa.wos_author_id,a.raw_address FROM wos_author_addresses aa "
            "JOIN wos_addresses a ON a.address_id=aa.address_id "
            "WHERE a.ut=? ORDER BY a.order_index", (ut,)
        ).fetchall():
            addresses_by_author.setdefault(int(row["wos_author_id"]), []).append(row["raw_address"])

        unassigned_identifiers = [
            {"namespace": row["namespace"], "value": row["value"], "raw_value": row["raw_value"]}
            for row in con.execute(
                "SELECT namespace,value,raw_value FROM wos_author_identifiers "
                "WHERE ut=? AND wos_author_id IS NULL ORDER BY identifier_id", (ut,)
            ).fetchall()
        ]
        metric_columns = {
            str(row[1]) for row in con.execute("PRAGMA table_info(wos_record_metrics)").fetchall()
        }
        metric_select = (
            "SELECT observed_at,source_data_date,times_cited_wos,times_cited_total,batch_id "
            if "source_data_date" in metric_columns
            else "SELECT observed_at,NULL AS source_data_date,times_cited_wos,times_cited_total,batch_id "
        )
        metric_history = [
            dict(row)
            for row in con.execute(
                metric_select + "FROM wos_record_metrics WHERE ut=? ORDER BY observed_at,metric_id",
                (ut,),
            ).fetchall()
        ]
        raw_addresses = [
            dict(row)
            for row in con.execute(
                "SELECT address_id,order_index,raw_address FROM wos_addresses WHERE ut=? ORDER BY order_index",
                (ut,),
            ).fetchall()
        ]

    authors = []
    for author in record.get("authors", []):
        row = dict(author)
        aid = int(row["wos_author_id"])
        row["identifiers"] = identifiers_by_author.get(aid, [])
        row["addresses"] = addresses_by_author.get(aid, [])
        authors.append(row)
    record["authors"] = authors
    record["unassigned_author_identifiers"] = unassigned_identifiers
    record["addresses"] = raw_addresses
    record["metric_history"] = metric_history
    funding = dict(record.get("funding") or {})
    funding["items"] = parse_funding_items(funding.get("funding_agencies_raw"))
    record["funding"] = funding
    return record


def search_records(store: WosCorpusStore, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Search across the major WoS corpus dimensions, not only title/DOI."""
    q = query.strip().casefold()
    if not q:
        return []
    like = f"%{q}%"
    with store.connect() as con:
        rows = con.execute(
            """SELECT DISTINCT r.ut,r.doi,r.title,r.source_title,r.publication_year,
                              r.times_cited_wos,r.times_cited_total
               FROM wos_records r
               LEFT JOIN wos_authors a ON a.ut=r.ut
               LEFT JOIN wos_author_identifiers ai ON ai.ut=r.ut
               LEFT JOIN wos_keywords k ON k.ut=r.ut
               LEFT JOIN wos_organizations o ON o.ut=r.ut
               LEFT JOIN wos_classifications c ON c.ut=r.ut
               LEFT JOIN wos_funding f ON f.ut=r.ut
               WHERE lower(coalesce(r.title,'')) LIKE ?
                  OR lower(coalesce(r.doi,'')) LIKE ?
                  OR lower(coalesce(r.ut,'')) LIKE ?
                  OR lower(coalesce(r.source_title,'')) LIKE ?
                  OR lower(coalesce(a.full_name,a.au_name,'')) LIKE ?
                  OR lower(coalesce(ai.value,'')) LIKE ?
                  OR lower(coalesce(k.keyword,'')) LIKE ?
                  OR lower(coalesce(o.organization,'')) LIKE ?
                  OR lower(coalesce(c.value,'')) LIKE ?
                  OR lower(coalesce(f.funding_agencies_raw,'')) LIKE ?
                  OR lower(coalesce(f.funding_text_raw,'')) LIKE ?
               ORDER BY r.publication_year DESC,r.ut
               LIMIT ?""",
            (
                like, like, like, like, like, like,
                like, like, like, like, like,
                max(1, min(limit, 500)),
            ),
        ).fetchall()
    return [dict(row) for row in rows]


def rich_references(
    store: WosCorpusStore, ut: str, *, limit: int = 500, offset: int = 0
) -> list[dict[str, Any]]:
    """Return CR rows with locally resolved WoS target metadata when available."""
    with store.connect() as con:
        rows = con.execute(
            """SELECT cr.*,t.title AS target_title,t.doi AS target_doi,
                      t.source_title AS target_source_title,t.publication_year AS target_publication_year
               FROM wos_cited_references cr
               LEFT JOIN wos_records t ON t.ut=cr.target_ut
               WHERE cr.source_ut=? ORDER BY cr.order_index LIMIT ? OFFSET ?""",
            (ut, max(1, min(limit, 2000)), max(0, offset)),
        ).fetchall()
    return [dict(row) for row in rows]
