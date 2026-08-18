"""Independent SQLite storage for the local Web of Science background corpus.

Schema v3 treats every imported Full Record as an observation of a stable WoS UT.
Repeated UTs are expected: non-empty metadata is merged, CR payloads are unioned
without destructive replacement, and each observation records whether WoS actually
supplied the cited-reference list for that export.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .parser import (
    CR_COMPLETE,
    CR_COMPLETE_ZERO,
    CR_MISSING_FROM_EXPORT,
    CR_PARTIAL,
    CR_PRESENT_UNVERIFIED,
    CR_UNKNOWN,
    ParsedReference,
    ParsedWosRecord,
    normalize_author_key,
    normalize_doi,
    normalize_space,
    normalize_title,
    parse_records_with_stats,
)

SCHEMA_VERSION = 3

SCHEMA_SQL = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS wos_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wos_import_batches (
 batch_id INTEGER PRIMARY KEY,source_filename TEXT NOT NULL,source_sha256 TEXT NOT NULL,label TEXT,search_note TEXT,
 imported_at TEXT NOT NULL,record_count INTEGER NOT NULL DEFAULT 0,new_count INTEGER NOT NULL DEFAULT 0,updated_count INTEGER NOT NULL DEFAULT 0,
 cr_complete_count INTEGER NOT NULL DEFAULT 0,cr_complete_zero_count INTEGER NOT NULL DEFAULT 0,
 cr_missing_count INTEGER NOT NULL DEFAULT 0,cr_partial_count INTEGER NOT NULL DEFAULT 0,
 cr_unverified_count INTEGER NOT NULL DEFAULT 0,cr_unknown_count INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_wos_batches_sha ON wos_import_batches(source_sha256);
CREATE TABLE IF NOT EXISTS wos_records (
 ut TEXT PRIMARY KEY,doi TEXT,normalized_doi TEXT,title TEXT,normalized_title TEXT,source_title TEXT,
 source_abbrev_29 TEXT,source_iso_abbrev TEXT,publication_type_code TEXT,document_type TEXT,abstract TEXT,
 publication_year INTEGER,publication_date TEXT,early_access_date TEXT,early_access_year INTEGER,wos_data_date TEXT,
 volume TEXT,issue TEXT,begin_page TEXT,end_page TEXT,article_number TEXT,pmid TEXT,
 times_cited_wos INTEGER,times_cited_total INTEGER,reported_reference_count INTEGER,
 cr_status TEXT NOT NULL DEFAULT 'UNKNOWN',best_cr_count INTEGER NOT NULL DEFAULT 0,last_cr_batch_id INTEGER,
 raw_record TEXT NOT NULL,first_imported_at TEXT NOT NULL,last_imported_at TEXT NOT NULL,
 last_batch_id INTEGER NOT NULL REFERENCES wos_import_batches(batch_id));
CREATE INDEX IF NOT EXISTS ix_wos_records_doi ON wos_records(normalized_doi);
CREATE INDEX IF NOT EXISTS ix_wos_records_title ON wos_records(normalized_title);
CREATE INDEX IF NOT EXISTS ix_wos_records_year ON wos_records(publication_year);
CREATE INDEX IF NOT EXISTS ix_wos_records_cr_status ON wos_records(cr_status);
CREATE TABLE IF NOT EXISTS wos_authors (
 wos_author_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,
 au_name TEXT NOT NULL,full_name TEXT,normalized_au TEXT,normalized_full_name TEXT,UNIQUE(ut,order_index));
CREATE INDEX IF NOT EXISTS ix_wos_authors_ut ON wos_authors(ut,order_index);
CREATE INDEX IF NOT EXISTS ix_wos_authors_au ON wos_authors(normalized_au);
CREATE INDEX IF NOT EXISTS ix_wos_authors_full ON wos_authors(normalized_full_name);
CREATE TABLE IF NOT EXISTS wos_author_identifiers (
 identifier_id INTEGER PRIMARY KEY,wos_author_id INTEGER REFERENCES wos_authors(wos_author_id) ON DELETE CASCADE,
 ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,namespace TEXT NOT NULL,value TEXT NOT NULL,raw_value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_wos_identifiers_value ON wos_author_identifiers(namespace,value);
CREATE TABLE IF NOT EXISTS wos_addresses (
 address_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,
 raw_address TEXT NOT NULL,UNIQUE(ut,order_index));
CREATE TABLE IF NOT EXISTS wos_author_addresses (
 wos_author_id INTEGER NOT NULL REFERENCES wos_authors(wos_author_id) ON DELETE CASCADE,
 address_id INTEGER NOT NULL REFERENCES wos_addresses(address_id) ON DELETE CASCADE,PRIMARY KEY(wos_author_id,address_id));
CREATE TABLE IF NOT EXISTS wos_organizations (
 organization_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,
 organization TEXT NOT NULL,UNIQUE(ut,order_index));
CREATE TABLE IF NOT EXISTS wos_correspondence_groups (
 correspondence_group_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,
 raw_group TEXT NOT NULL,raw_address TEXT,UNIQUE(ut,order_index));
CREATE TABLE IF NOT EXISTS wos_correspondence_members (
 correspondence_group_id INTEGER NOT NULL REFERENCES wos_correspondence_groups(correspondence_group_id) ON DELETE CASCADE,
 wos_author_id INTEGER REFERENCES wos_authors(wos_author_id) ON DELETE SET NULL,raw_member_name TEXT NOT NULL,normalized_member_name TEXT,
 PRIMARY KEY(correspondence_group_id,raw_member_name));
CREATE TABLE IF NOT EXISTS wos_emails (
 email_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,email TEXT NOT NULL,
 UNIQUE(ut,order_index));
CREATE TABLE IF NOT EXISTS wos_keywords (
 keyword_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,
 keyword_type TEXT NOT NULL CHECK(keyword_type IN ('AUTHOR','KEYWORDS_PLUS')),order_index INTEGER NOT NULL,keyword TEXT NOT NULL,
 UNIQUE(ut,keyword_type,order_index));
CREATE INDEX IF NOT EXISTS ix_wos_keywords_keyword ON wos_keywords(keyword);
CREATE TABLE IF NOT EXISTS wos_classifications (
 classification_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,
 namespace TEXT NOT NULL CHECK(namespace IN ('WC','SC','TO','WE')),order_index INTEGER NOT NULL,value TEXT NOT NULL,
 UNIQUE(ut,namespace,order_index));
CREATE TABLE IF NOT EXISTS wos_funding (
 ut TEXT PRIMARY KEY REFERENCES wos_records(ut) ON DELETE CASCADE,funding_agencies_raw TEXT,funding_text_raw TEXT);
CREATE TABLE IF NOT EXISTS wos_cited_references (
 cited_reference_id INTEGER PRIMARY KEY,source_ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,order_index INTEGER NOT NULL,
 raw_reference TEXT NOT NULL,cited_doi TEXT,cited_author TEXT,cited_year INTEGER,cited_source TEXT,volume TEXT,page TEXT,
 target_ut TEXT REFERENCES wos_records(ut) ON DELETE SET NULL,UNIQUE(source_ut,order_index));
CREATE INDEX IF NOT EXISTS ix_wos_cr_source ON wos_cited_references(source_ut,order_index);
CREATE INDEX IF NOT EXISTS ix_wos_cr_doi ON wos_cited_references(cited_doi);
CREATE INDEX IF NOT EXISTS ix_wos_cr_target ON wos_cited_references(target_ut);
CREATE TABLE IF NOT EXISTS wos_record_metrics (
 metric_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,
 batch_id INTEGER NOT NULL REFERENCES wos_import_batches(batch_id) ON DELETE CASCADE,observed_at TEXT NOT NULL,source_data_date TEXT,
 times_cited_wos INTEGER,times_cited_total INTEGER,UNIQUE(ut,batch_id));
CREATE TABLE IF NOT EXISTS wos_record_observations (
 observation_id INTEGER PRIMARY KEY,ut TEXT NOT NULL REFERENCES wos_records(ut) ON DELETE CASCADE,
 batch_id INTEGER NOT NULL REFERENCES wos_import_batches(batch_id) ON DELETE CASCADE,observed_at TEXT NOT NULL,source_data_date TEXT,
 cr_tag_present INTEGER NOT NULL,parsed_cr_count INTEGER NOT NULL,reported_reference_count INTEGER,cr_export_status TEXT NOT NULL,
 raw_record TEXT NOT NULL,UNIQUE(ut,batch_id));
CREATE INDEX IF NOT EXISTS ix_wos_observations_ut ON wos_record_observations(ut,observation_id);
CREATE INDEX IF NOT EXISTS ix_wos_observations_cr_status ON wos_record_observations(cr_export_status);
"""

V2_RECORD_COLUMNS = {
    "source_abbrev_29": "TEXT",
    "source_iso_abbrev": "TEXT",
    "publication_type_code": "TEXT",
    "early_access_date": "TEXT",
    "early_access_year": "INTEGER",
    "wos_data_date": "TEXT",
}
V3_RECORD_COLUMNS = {
    "reported_reference_count": "INTEGER",
    "cr_status": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    "best_cr_count": "INTEGER NOT NULL DEFAULT 0",
    "last_cr_batch_id": "INTEGER",
}
V3_BATCH_COLUMNS = {
    "cr_complete_count": "INTEGER NOT NULL DEFAULT 0",
    "cr_complete_zero_count": "INTEGER NOT NULL DEFAULT 0",
    "cr_missing_count": "INTEGER NOT NULL DEFAULT 0",
    "cr_partial_count": "INTEGER NOT NULL DEFAULT 0",
    "cr_unverified_count": "INTEGER NOT NULL DEFAULT 0",
    "cr_unknown_count": "INTEGER NOT NULL DEFAULT 0",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identifier_name(raw: str) -> str:
    return raw.rsplit("/", 1)[0].strip() if "/" in raw else raw.strip()


def _identifier_value(raw: str) -> str:
    return raw.rsplit("/", 1)[1].strip() if "/" in raw else raw.strip()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _next_index(con: sqlite3.Connection, table: str, where: str, params: tuple[Any, ...], column: str = "order_index") -> int:
    row = con.execute(f"SELECT coalesce(max({column}),-1)+1 FROM {table} WHERE {where}", params).fetchone()
    return int(row[0])


def _ref_key(reference: dict[str, Any] | ParsedReference) -> str:
    doi = reference["cited_doi"] if isinstance(reference, dict) else reference.doi
    if doi:
        return "doi:" + str(doi).casefold()
    raw = reference["raw_reference"] if isinstance(reference, dict) else reference.raw_text
    return "raw:" + (normalize_space(str(raw)) or str(raw)).casefold()


class WosCorpusStore:
    """Writable owner and read service for an independent local WoS corpus."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect(write=True) as con:
            con.executescript(SCHEMA_SQL)
            self._migrate_schema(con)
            con.execute(
                "INSERT INTO wos_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _migrate_schema(con: sqlite3.Connection) -> None:
        record_columns = _columns(con, "wos_records")
        for name, sql_type in {**V2_RECORD_COLUMNS, **V3_RECORD_COLUMNS}.items():
            if name not in record_columns:
                con.execute(f"ALTER TABLE wos_records ADD COLUMN {name} {sql_type}")
        metric_columns = _columns(con, "wos_record_metrics")
        if "source_data_date" not in metric_columns:
            con.execute("ALTER TABLE wos_record_metrics ADD COLUMN source_data_date TEXT")
        batch_columns = _columns(con, "wos_import_batches")
        for name, sql_type in V3_BATCH_COLUMNS.items():
            if name not in batch_columns:
                con.execute(f"ALTER TABLE wos_import_batches ADD COLUMN {name} {sql_type}")
        con.execute(
            """UPDATE wos_records
               SET best_cr_count=(SELECT count(*) FROM wos_cited_references cr WHERE cr.source_ut=wos_records.ut)
               WHERE best_cr_count=0"""
        )
        con.execute(
            """UPDATE wos_records SET cr_status='PRESENT_UNVERIFIED'
               WHERE cr_status='UNKNOWN' AND best_cr_count>0"""
        )

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if write:
            con = sqlite3.connect(self.path)
        else:
            if not self.path.exists():
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

    def import_file(self, path: str | Path, *, label: str | None = None, search_note: str | None = None) -> dict[str, Any]:
        source = Path(path)
        data = source.read_bytes()
        return self.import_text(
            data.decode("utf-8-sig"),
            source_filename=source.name,
            source_sha256=_sha256_bytes(data),
            label=label,
            search_note=search_note,
        )

    def import_text(
        self,
        text: str,
        *,
        source_filename: str = "<memory>",
        source_sha256: str | None = None,
        label: str | None = None,
        search_note: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        records, skipped_without_ut = parse_records_with_stats(text)
        if not records:
            raise ValueError("no complete WoS records found in tagged plain-text input")
        digest = source_sha256 or _sha256_bytes(text.encode("utf-8"))
        imported_at = _now()
        status_counts = {
            CR_COMPLETE: 0,
            CR_COMPLETE_ZERO: 0,
            CR_MISSING_FROM_EXPORT: 0,
            CR_PARTIAL: 0,
            CR_PRESENT_UNVERIFIED: 0,
            CR_UNKNOWN: 0,
        }
        with self.connect(write=True) as con:
            cur = con.execute(
                "INSERT INTO wos_import_batches(source_filename,source_sha256,label,search_note,imported_at) VALUES(?,?,?,?,?)",
                (source_filename, digest, label, search_note, imported_at),
            )
            batch_id = int(cur.lastrowid)
            new_count = updated_count = 0
            for record in records:
                existed = con.execute("SELECT 1 FROM wos_records WHERE ut=?", (record.ut,)).fetchone() is not None
                self._merge_record(con, record, batch_id=batch_id, imported_at=imported_at)
                status_counts[record.cr_export_status] = status_counts.get(record.cr_export_status, 0) + 1
                new_count += int(not existed)
                updated_count += int(existed)
            self.resolve_citation_targets(con)
            con.execute(
                """UPDATE wos_import_batches SET record_count=?,new_count=?,updated_count=?,
                   cr_complete_count=?,cr_complete_zero_count=?,cr_missing_count=?,cr_partial_count=?,cr_unverified_count=?,cr_unknown_count=?
                   WHERE batch_id=?""",
                (
                    len(records), new_count, updated_count,
                    status_counts[CR_COMPLETE], status_counts[CR_COMPLETE_ZERO], status_counts[CR_MISSING_FROM_EXPORT],
                    status_counts[CR_PARTIAL], status_counts[CR_PRESENT_UNVERIFIED], status_counts[CR_UNKNOWN], batch_id,
                ),
            )
        return {
            "batch_id": batch_id,
            "source_filename": source_filename,
            "source_sha256": digest,
            "raw_record_count": len(records) + skipped_without_ut,
            "record_count": len(records),
            "skipped_without_ut": skipped_without_ut,
            "new_count": new_count,
            "updated_count": updated_count,
            "merged_count": updated_count,
            "cr_complete_count": status_counts[CR_COMPLETE],
            "cr_complete_zero_count": status_counts[CR_COMPLETE_ZERO],
            "cr_missing_from_export_count": status_counts[CR_MISSING_FROM_EXPORT],
            "cr_partial_count": status_counts[CR_PARTIAL],
            "cr_present_unverified_count": status_counts[CR_PRESENT_UNVERIFIED],
            "cr_unknown_count": status_counts[CR_UNKNOWN],
        }

    def _merge_record(self, con: sqlite3.Connection, record: ParsedWosRecord, *, batch_id: int, imported_at: str) -> None:
        old = con.execute("SELECT first_imported_at FROM wos_records WHERE ut=?", (record.ut,)).fetchone()
        first = old[0] if old else imported_at
        last_cr_batch = batch_id if (record.cr_tag_present or record.reported_reference_count is not None) else None
        con.execute(
            """INSERT INTO wos_records(
               ut,doi,normalized_doi,title,normalized_title,source_title,source_abbrev_29,source_iso_abbrev,
               publication_type_code,document_type,abstract,publication_year,publication_date,early_access_date,
               early_access_year,wos_data_date,volume,issue,begin_page,end_page,article_number,pmid,
               times_cited_wos,times_cited_total,reported_reference_count,cr_status,best_cr_count,last_cr_batch_id,
               raw_record,first_imported_at,last_imported_at,last_batch_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(ut) DO UPDATE SET
               doi=coalesce(excluded.doi,wos_records.doi),
               normalized_doi=coalesce(excluded.normalized_doi,wos_records.normalized_doi),
               title=coalesce(excluded.title,wos_records.title),
               normalized_title=coalesce(excluded.normalized_title,wos_records.normalized_title),
               source_title=coalesce(excluded.source_title,wos_records.source_title),
               source_abbrev_29=coalesce(excluded.source_abbrev_29,wos_records.source_abbrev_29),
               source_iso_abbrev=coalesce(excluded.source_iso_abbrev,wos_records.source_iso_abbrev),
               publication_type_code=coalesce(excluded.publication_type_code,wos_records.publication_type_code),
               document_type=coalesce(excluded.document_type,wos_records.document_type),
               abstract=coalesce(excluded.abstract,wos_records.abstract),
               publication_year=coalesce(excluded.publication_year,wos_records.publication_year),
               publication_date=coalesce(excluded.publication_date,wos_records.publication_date),
               early_access_date=coalesce(excluded.early_access_date,wos_records.early_access_date),
               early_access_year=coalesce(excluded.early_access_year,wos_records.early_access_year),
               wos_data_date=coalesce(excluded.wos_data_date,wos_records.wos_data_date),
               volume=coalesce(excluded.volume,wos_records.volume),issue=coalesce(excluded.issue,wos_records.issue),
               begin_page=coalesce(excluded.begin_page,wos_records.begin_page),end_page=coalesce(excluded.end_page,wos_records.end_page),
               article_number=coalesce(excluded.article_number,wos_records.article_number),pmid=coalesce(excluded.pmid,wos_records.pmid),
               times_cited_wos=coalesce(excluded.times_cited_wos,wos_records.times_cited_wos),
               times_cited_total=coalesce(excluded.times_cited_total,wos_records.times_cited_total),
               reported_reference_count=CASE
                 WHEN excluded.reported_reference_count IS NULL THEN wos_records.reported_reference_count
                 WHEN wos_records.reported_reference_count IS NULL THEN excluded.reported_reference_count
                 WHEN excluded.reported_reference_count>wos_records.reported_reference_count THEN excluded.reported_reference_count
                 ELSE wos_records.reported_reference_count END,
               last_cr_batch_id=coalesce(excluded.last_cr_batch_id,wos_records.last_cr_batch_id),
               raw_record=excluded.raw_record,last_imported_at=excluded.last_imported_at,last_batch_id=excluded.last_batch_id""",
            (
                record.ut, record.doi, normalize_doi(record.doi), record.title, record.normalized_title,
                record.source_title, record.source_abbrev_29, record.source_iso_abbrev, record.publication_type_code,
                record.document_type, record.abstract, record.publication_year, record.publication_date,
                record.early_access_date, record.early_access_year, record.wos_data_date, record.volume, record.issue,
                record.begin_page, record.end_page, record.article_number, record.pmid, record.times_cited_wos,
                record.times_cited_total, record.reported_reference_count, record.cr_export_status, 0, last_cr_batch,
                record.raw_record.raw_text, first, imported_at, batch_id,
            ),
        )

        self._merge_authors(con, record)
        self._merge_identifiers(con, record)
        self._merge_addresses(con, record)
        self._merge_organizations(con, record)
        self._merge_correspondence(con, record)
        self._merge_emails(con, record)
        self._merge_keywords(con, record)
        self._merge_classifications(con, record)
        self._merge_funding(con, record)
        self._merge_references(con, record)

        con.execute(
            "INSERT OR REPLACE INTO wos_record_metrics(ut,batch_id,observed_at,source_data_date,times_cited_wos,times_cited_total) VALUES(?,?,?,?,?,?)",
            (record.ut, batch_id, imported_at, record.wos_data_date, record.times_cited_wos, record.times_cited_total),
        )
        con.execute(
            """INSERT OR REPLACE INTO wos_record_observations(
               ut,batch_id,observed_at,source_data_date,cr_tag_present,parsed_cr_count,reported_reference_count,cr_export_status,raw_record)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                record.ut, batch_id, imported_at, record.wos_data_date, int(record.cr_tag_present), len(record.references),
                record.reported_reference_count, record.cr_export_status, record.raw_record.raw_text,
            ),
        )
        self._refresh_cr_status(con, record.ut)

    @staticmethod
    def _author_maps(con: sqlite3.Connection, ut: str) -> tuple[dict[str, int], dict[str, int]]:
        au_map: dict[str, int] = {}
        full_map: dict[str, int] = {}
        for row in con.execute("SELECT wos_author_id,au_name,full_name FROM wos_authors WHERE ut=?", (ut,)).fetchall():
            au_key = normalize_author_key(row["au_name"])
            full_key = normalize_author_key(row["full_name"])
            if au_key:
                au_map[au_key] = int(row["wos_author_id"])
            if full_key:
                full_map[full_key] = int(row["wos_author_id"])
        return au_map, full_map

    def _merge_authors(self, con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        for author in record.authors:
            con.execute(
                """INSERT INTO wos_authors(ut,order_index,au_name,full_name,normalized_au,normalized_full_name)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(ut,order_index) DO UPDATE SET
                   au_name=coalesce(excluded.au_name,wos_authors.au_name),
                   full_name=coalesce(excluded.full_name,wos_authors.full_name),
                   normalized_au=coalesce(excluded.normalized_au,wos_authors.normalized_au),
                   normalized_full_name=coalesce(excluded.normalized_full_name,wos_authors.normalized_full_name)""",
                (record.ut, author.order_index, author.au_name, author.full_name,
                 normalize_author_key(author.au_name), normalize_author_key(author.full_name)),
            )

    def _identifier_author_id(self, con: sqlite3.Connection, record: ParsedWosRecord, raw: str) -> int | None:
        au_map, full_map = self._author_maps(con, record.ut)
        key = normalize_author_key(_identifier_name(raw))
        if not key:
            return None
        if key in full_map:
            return full_map[key]
        tokens = key.split()
        candidates: list[int] = []
        for full_key, author_id in full_map.items():
            parts = full_key.split()
            if parts and tokens and parts[0] == tokens[0] and (
                len(tokens) == 1 or any(p.startswith(tokens[-1]) or tokens[-1].startswith(p) for p in parts[1:])
            ):
                candidates.append(author_id)
        return candidates[0] if len(set(candidates)) == 1 else None

    def _merge_identifiers(self, con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        for namespace, values in (("RESEARCHER_ID", record.researcher_ids), ("ORCID", record.orcids)):
            for raw in values:
                value = _identifier_value(raw)
                exists = con.execute(
                    "SELECT identifier_id FROM wos_author_identifiers WHERE ut=? AND namespace=? AND value=?",
                    (record.ut, namespace, value),
                ).fetchone()
                author_id = self._identifier_author_id(con, record, raw)
                if exists:
                    con.execute(
                        "UPDATE wos_author_identifiers SET wos_author_id=coalesce(?,wos_author_id),raw_value=? WHERE identifier_id=?",
                        (author_id, raw, int(exists[0])),
                    )
                else:
                    con.execute(
                        "INSERT INTO wos_author_identifiers(wos_author_id,ut,namespace,value,raw_value) VALUES(?,?,?,?,?)",
                        (author_id, record.ut, namespace, value, raw),
                    )

    def _merge_addresses(self, con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        _, full_map = self._author_maps(con, record.ut)
        for address in record.addresses:
            existing = con.execute(
                "SELECT address_id FROM wos_addresses WHERE ut=? AND raw_address=?", (record.ut, address.address)
            ).fetchone()
            if existing:
                address_id = int(existing[0])
            else:
                order_index = _next_index(con, "wos_addresses", "ut=?", (record.ut,))
                cur = con.execute(
                    "INSERT INTO wos_addresses(ut,order_index,raw_address) VALUES(?,?,?)",
                    (record.ut, order_index, address.address),
                )
                address_id = int(cur.lastrowid)
            for name in address.author_names:
                author_id = full_map.get(normalize_author_key(name) or "")
                if author_id is not None:
                    con.execute(
                        "INSERT OR IGNORE INTO wos_author_addresses(wos_author_id,address_id) VALUES(?,?)",
                        (author_id, address_id),
                    )

    @staticmethod
    def _merge_organizations(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        existing = {str(row[0]).casefold() for row in con.execute("SELECT organization FROM wos_organizations WHERE ut=?", (record.ut,))}
        next_index = _next_index(con, "wos_organizations", "ut=?", (record.ut,))
        for value in record.organizations:
            if value.casefold() in existing:
                continue
            con.execute("INSERT INTO wos_organizations(ut,order_index,organization) VALUES(?,?,?)", (record.ut, next_index, value))
            existing.add(value.casefold())
            next_index += 1

    def _merge_correspondence(self, con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        au_map, _ = self._author_maps(con, record.ut)
        next_index = _next_index(con, "wos_correspondence_groups", "ut=?", (record.ut,))
        for group in record.correspondence_groups:
            existing = con.execute(
                "SELECT correspondence_group_id FROM wos_correspondence_groups WHERE ut=? AND raw_group=?",
                (record.ut, group.raw_group),
            ).fetchone()
            if existing:
                group_id = int(existing[0])
            else:
                cur = con.execute(
                    "INSERT INTO wos_correspondence_groups(ut,order_index,raw_group,raw_address) VALUES(?,?,?,?)",
                    (record.ut, next_index, group.raw_group, group.address),
                )
                group_id = int(cur.lastrowid)
                next_index += 1
            for name in group.member_names:
                key = normalize_author_key(name)
                con.execute(
                    """INSERT INTO wos_correspondence_members(correspondence_group_id,wos_author_id,raw_member_name,normalized_member_name)
                       VALUES(?,?,?,?) ON CONFLICT(correspondence_group_id,raw_member_name) DO UPDATE SET
                       wos_author_id=coalesce(excluded.wos_author_id,wos_correspondence_members.wos_author_id),
                       normalized_member_name=coalesce(excluded.normalized_member_name,wos_correspondence_members.normalized_member_name)""",
                    (group_id, au_map.get(key or ""), name, key),
                )

    @staticmethod
    def _merge_emails(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        existing = {str(row[0]).casefold() for row in con.execute("SELECT email FROM wos_emails WHERE ut=?", (record.ut,))}
        next_index = _next_index(con, "wos_emails", "ut=?", (record.ut,))
        for email in record.emails:
            if email.casefold() in existing:
                continue
            con.execute("INSERT INTO wos_emails(ut,order_index,email) VALUES(?,?,?)", (record.ut, next_index, email))
            existing.add(email.casefold())
            next_index += 1

    @staticmethod
    def _merge_keywords(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        for kind, values in (("AUTHOR", record.author_keywords), ("KEYWORDS_PLUS", record.keywords_plus)):
            existing = {str(row[0]).casefold() for row in con.execute(
                "SELECT keyword FROM wos_keywords WHERE ut=? AND keyword_type=?", (record.ut, kind)
            )}
            next_index = _next_index(con, "wos_keywords", "ut=? AND keyword_type=?", (record.ut, kind))
            for value in values:
                if value.casefold() in existing:
                    continue
                con.execute(
                    "INSERT INTO wos_keywords(ut,keyword_type,order_index,keyword) VALUES(?,?,?,?)",
                    (record.ut, kind, next_index, value),
                )
                existing.add(value.casefold())
                next_index += 1

    @staticmethod
    def _merge_classifications(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        for namespace, values in record.classifications.items():
            existing = {str(row[0]).casefold() for row in con.execute(
                "SELECT value FROM wos_classifications WHERE ut=? AND namespace=?", (record.ut, namespace)
            )}
            next_index = _next_index(con, "wos_classifications", "ut=? AND namespace=?", (record.ut, namespace))
            for value in values:
                if value.casefold() in existing:
                    continue
                con.execute(
                    "INSERT INTO wos_classifications(ut,namespace,order_index,value) VALUES(?,?,?,?)",
                    (record.ut, namespace, next_index, value),
                )
                existing.add(value.casefold())
                next_index += 1

    @staticmethod
    def _merge_funding(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        if not (record.funding_agencies or record.funding_text):
            return
        con.execute(
            """INSERT INTO wos_funding(ut,funding_agencies_raw,funding_text_raw) VALUES(?,?,?)
               ON CONFLICT(ut) DO UPDATE SET
               funding_agencies_raw=coalesce(excluded.funding_agencies_raw,wos_funding.funding_agencies_raw),
               funding_text_raw=coalesce(excluded.funding_text_raw,wos_funding.funding_text_raw)""",
            (record.ut, record.funding_agencies, record.funding_text),
        )

    @staticmethod
    def _merge_references(con: sqlite3.Connection, record: ParsedWosRecord) -> None:
        if not record.references:
            return
        existing_rows = [dict(row) for row in con.execute(
            "SELECT * FROM wos_cited_references WHERE source_ut=? ORDER BY order_index", (record.ut,)
        ).fetchall()]
        merged: list[dict[str, Any] | ParsedReference] = list(existing_rows)
        seen = {_ref_key(row) for row in existing_rows}
        for reference in record.references:
            key = _ref_key(reference)
            if key not in seen:
                merged.append(reference)
                seen.add(key)
        con.execute("DELETE FROM wos_cited_references WHERE source_ut=?", (record.ut,))
        for order_index, reference in enumerate(merged):
            if isinstance(reference, dict):
                values = (
                    reference["raw_reference"], reference["cited_doi"], reference["cited_author"],
                    reference["cited_year"], reference["cited_source"], reference["volume"], reference["page"],
                )
            else:
                values = (
                    reference.raw_text, reference.doi, reference.cited_author, reference.cited_year,
                    reference.cited_source, reference.volume, reference.page,
                )
            con.execute(
                """INSERT INTO wos_cited_references(source_ut,order_index,raw_reference,cited_doi,cited_author,cited_year,cited_source,volume,page,target_ut)
                   VALUES(?,?,?,?,?,?,?,?,?,NULL)""",
                (record.ut, order_index, *values),
            )

    @staticmethod
    def _refresh_cr_status(con: sqlite3.Connection, ut: str) -> None:
        canonical_count = int(con.execute(
            "SELECT count(*) FROM wos_cited_references WHERE source_ut=?", (ut,)
        ).fetchone()[0])
        observations = [dict(row) for row in con.execute(
            "SELECT cr_export_status,reported_reference_count FROM wos_record_observations WHERE ut=?", (ut,)
        ).fetchall()]
        statuses = {str(row["cr_export_status"]) for row in observations}
        reported = [int(row["reported_reference_count"]) for row in observations if row["reported_reference_count"] is not None]
        max_reported = max(reported) if reported else None
        complete_counts = [
            int(row["reported_reference_count"])
            for row in observations
            if row["cr_export_status"] == CR_COMPLETE and row["reported_reference_count"] is not None
        ]
        if canonical_count == 0:
            if CR_COMPLETE_ZERO in statuses:
                status = CR_COMPLETE_ZERO
            elif CR_MISSING_FROM_EXPORT in statuses:
                status = CR_MISSING_FROM_EXPORT
            else:
                status = CR_UNKNOWN
        elif complete_counts and canonical_count == max(complete_counts):
            status = CR_COMPLETE
        elif complete_counts:
            status = "MERGED"
        else:
            status = "PARTIAL_OR_UNVERIFIED"
        con.execute(
            "UPDATE wos_records SET cr_status=?,best_cr_count=?,reported_reference_count=coalesce(?,reported_reference_count) WHERE ut=?",
            (status, canonical_count, max_reported, ut),
        )

    @staticmethod
    def resolve_citation_targets(con: sqlite3.Connection) -> int:
        con.execute(
            """UPDATE wos_cited_references SET target_ut=(
                   SELECT MIN(r.ut) FROM wos_records r
                   WHERE r.normalized_doi=wos_cited_references.cited_doi HAVING COUNT(*)=1)
               WHERE cited_doi IS NOT NULL"""
        )
        con.execute(
            """UPDATE wos_cited_references SET target_ut=NULL WHERE cited_doi IS NOT NULL AND
               (SELECT COUNT(*) FROM wos_records r WHERE r.normalized_doi=wos_cited_references.cited_doi)<>1"""
        )
        return int(con.execute("SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL").fetchone()[0])

    def stats(self) -> dict[str, int]:
        with self.connect() as con:
            def count(sql: str) -> int:
                return int(con.execute(sql).fetchone()[0])
            return {
                "records": count("SELECT count(*) FROM wos_records"),
                "authors": count("SELECT count(*) FROM wos_authors"),
                "corresponding_members": count("SELECT count(*) FROM wos_correspondence_members"),
                "cited_references": count("SELECT count(*) FROM wos_cited_references"),
                "resolved_citation_edges": count("SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL"),
                "import_batches": count("SELECT count(*) FROM wos_import_batches"),
                "record_observations": count("SELECT count(*) FROM wos_record_observations"),
                "records_cr_complete": count("SELECT count(*) FROM wos_records WHERE cr_status IN ('COMPLETE','COMPLETE_ZERO')"),
                "records_cr_missing": count("SELECT count(*) FROM wos_records WHERE cr_status='MISSING_FROM_EXPORT'"),
                "records_cr_partial_or_unverified": count("SELECT count(*) FROM wos_records WHERE cr_status IN ('PARTIAL_OR_UNVERIFIED','MERGED','PRESENT_UNVERIFIED')"),
            }

    def find_by_doi(self, doi: str) -> list[dict[str, Any]]:
        value = normalize_doi(doi)
        if not value:
            return []
        with self.connect() as con:
            return [dict(row) for row in con.execute(
                "SELECT * FROM wos_records WHERE normalized_doi=? ORDER BY ut", (value,)
            ).fetchall()]

    def find_by_exact_title(self, title: str) -> list[dict[str, Any]]:
        value = normalize_title(title)
        if not value:
            return []
        with self.connect() as con:
            return [dict(row) for row in con.execute(
                "SELECT * FROM wos_records WHERE normalized_title=? ORDER BY publication_year,ut", (value,)
            ).fetchall()]

    def search(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        q = query.strip().casefold()
        if not q:
            return []
        like = f"%{q}%"
        with self.connect() as con:
            rows = con.execute(
                """SELECT DISTINCT r.* FROM wos_records r
                   LEFT JOIN wos_authors a ON a.ut=r.ut LEFT JOIN wos_keywords k ON k.ut=r.ut
                   WHERE lower(coalesce(r.title,'')) LIKE ? OR lower(coalesce(r.doi,'')) LIKE ?
                      OR lower(coalesce(r.ut,'')) LIKE ? OR lower(coalesce(r.source_title,'')) LIKE ?
                      OR lower(coalesce(a.full_name,a.au_name,'')) LIKE ? OR lower(coalesce(k.keyword,'')) LIKE ?
                   ORDER BY r.publication_year DESC,r.ut LIMIT ?""",
                (like, like, like, like, like, like, max(1, min(limit, 500))),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_record(self, ut: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM wos_records WHERE ut=?", (ut,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            authors = [dict(r) for r in con.execute(
                "SELECT * FROM wos_authors WHERE ut=? ORDER BY order_index", (ut,)
            ).fetchall()]
            groups = []
            for group in con.execute(
                "SELECT * FROM wos_correspondence_groups WHERE ut=? ORDER BY order_index", (ut,)
            ).fetchall():
                members = [dict(r) for r in con.execute(
                    """SELECT m.*,a.au_name,a.full_name FROM wos_correspondence_members m
                       LEFT JOIN wos_authors a ON a.wos_author_id=m.wos_author_id
                       WHERE m.correspondence_group_id=? ORDER BY m.rowid""",
                    (group["correspondence_group_id"],),
                ).fetchall()]
                groups.append({**dict(group), "members": members})
            funding = con.execute("SELECT * FROM wos_funding WHERE ut=?", (ut,)).fetchone()
            result.update(
                authors=authors,
                correspondence_groups=groups,
                emails=[row["email"] for row in con.execute(
                    "SELECT email FROM wos_emails WHERE ut=? ORDER BY order_index", (ut,)
                ).fetchall()],
                keywords=[dict(row) for row in con.execute(
                    "SELECT keyword_type,keyword FROM wos_keywords WHERE ut=? ORDER BY keyword_type,order_index", (ut,)
                ).fetchall()],
                classifications=[dict(row) for row in con.execute(
                    "SELECT namespace,value FROM wos_classifications WHERE ut=? ORDER BY namespace,order_index", (ut,)
                ).fetchall()],
                organizations=[row["organization"] for row in con.execute(
                    "SELECT organization FROM wos_organizations WHERE ut=? ORDER BY order_index", (ut,)
                ).fetchall()],
                funding=dict(funding) if funding else {},
                reference_count=int(con.execute(
                    "SELECT count(*) FROM wos_cited_references WHERE source_ut=?", (ut,)
                ).fetchone()[0]),
                resolved_reference_count=int(con.execute(
                    "SELECT count(*) FROM wos_cited_references WHERE source_ut=? AND target_ut IS NOT NULL", (ut,)
                ).fetchone()[0]),
                observation_count=int(con.execute(
                    "SELECT count(*) FROM wos_record_observations WHERE ut=?", (ut,)
                ).fetchone()[0]),
            )
            return result

    def list_observations(self, ut: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(row) for row in con.execute(
                """SELECT o.observation_id,o.ut,o.batch_id,o.observed_at,o.source_data_date,o.cr_tag_present,
                          o.parsed_cr_count,o.reported_reference_count,o.cr_export_status,b.source_filename,b.source_sha256,b.label,b.search_note
                   FROM wos_record_observations o JOIN wos_import_batches b ON b.batch_id=o.batch_id
                   WHERE o.ut=? ORDER BY o.observation_id DESC LIMIT ?""",
                (ut, max(1, min(limit, 1000))),
            ).fetchall()]

    def list_references(self, ut: str, *, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as con:
            return [dict(row) for row in con.execute(
                "SELECT * FROM wos_cited_references WHERE source_ut=? ORDER BY order_index LIMIT ? OFFSET ?",
                (ut, max(1, min(limit, 2000)), max(0, offset)),
            ).fetchall()]

    def citation_frontier(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """SELECT cited_doi,count(*) AS cited_by_count,min(cited_author) AS cited_author,
                          min(cited_year) AS cited_year,min(cited_source) AS cited_source
                   FROM wos_cited_references WHERE cited_doi IS NOT NULL AND target_ut IS NULL
                   GROUP BY cited_doi ORDER BY cited_by_count DESC,cited_doi LIMIT ?""",
                (max(1, min(limit, 1000)),),
            ).fetchall()
            return [dict(row) for row in rows]
