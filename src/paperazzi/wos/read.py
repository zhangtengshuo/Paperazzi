"""Rich read projection over the normalized independent WoS corpus."""
from __future__ import annotations

import re
from typing import Any

from .store import WosCorpusStore

_FUNDING_ITEM_RE = re.compile(r"^(.*?)(?:\s*\[([^\]]+)\])?$")


def parse_funding_items(raw_fu: str | None) -> list[dict[str, Any]]:
    """Conservatively split WoS FU into funder/grant display/search items.

    Raw FU/FX remain authoritative and are always retained.  This helper only adds
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
        metric_history = [dict(row) for row in con.execute(
            "SELECT observed_at,times_cited_wos,times_cited_total,batch_id "
            "FROM wos_record_metrics WHERE ut=? ORDER BY observed_at,metric_id", (ut,)
        ).fetchall()]
        raw_addresses = [dict(row) for row in con.execute(
            "SELECT address_id,order_index,raw_address FROM wos_addresses WHERE ut=? ORDER BY order_index", (ut,)
        ).fetchall()]

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
