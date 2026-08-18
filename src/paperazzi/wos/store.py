"""Independent SQLite storage for the local Web of Science background corpus."""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .parser import ParsedWosRecord, normalize_author_key, normalize_doi, normalize_title, parse_records

SCHEMA_VERSION = 1

SCHEMA_SQL = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS wos_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wos_import_batches (
 batch_id INTEGER PRIMARY KEY,source_filename TEXT NOT NULL,source_sha256 TEXT NOT NULL,label TEXT,search_note TEXT,
 imported_at TEXT NOT NULL,record_count INTEGER NOT NULL DEFAULT 0,new_count INTEGER NOT NULL DEFAULT 0,updated_count INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_wos_batches_sha ON wos_import_batches(source_sha256);
CREATE TABLE IF NOT EXISTS wos_records (
 ut TEXT PRIMARY KEY,doi TEXT,normalized_doi TEXT,title TEXT,normalized_title TEXT,source_title TEXT,document_type TEXT,abstract TEXT,
 publication_year INTEGER,publication_date TEXT,volume TEXT,issue TEXT,begin_page TEXT,end_page TEXT,article_number TEXT,pmid TEXT,
 times_cited_wos INTEGER,times_cited_total INTEGER,raw_record TEXT NOT NULL,first_imported_at TEXT NOT NULL,last_imported_at TEXT NOT NULL,
 last_batch_id INTEGER NOT NULL REFERENCES wos_import_batches(batch_id));
CREATE INDEX IF NOT EXISTS ix_wos_records_doi ON wos_records(normalized_doi);
CREATE INDEX IF NOT EXISTS ix_wos_records_title ON wos_records(normalized_title);
CREATE INDEX IF NOT EXISTS ix_wos_records_year ON wos_records(publication_year);
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
 batch_id INTEGER NOT NULL REFERENCES wos_import_batches(batch_id) ON DELETE CASCADE,observed_at TEXT NOT NULL,
 times_cited_wos INTEGER,times_cited_total INTEGER,UNIQUE(ut,batch_id));
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identifier_name(raw: str) -> str:
    return raw.rsplit("/",1)[0].strip() if "/" in raw else raw.strip()


def _identifier_value(raw: str) -> str:
    return raw.rsplit("/",1)[1].strip() if "/" in raw else raw.strip()


class WosCorpusStore:
    """Writable owner and read service for an independent local WoS corpus."""
    def __init__(self,path: str|Path): self.path=Path(path)

    def initialize(self)->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect(write=True) as con:
            con.executescript(SCHEMA_SQL)
            con.execute("INSERT INTO wos_meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(SCHEMA_VERSION),))

    @contextmanager
    def connect(self,*,write:bool=False)->Iterator[sqlite3.Connection]:
        if write: con=sqlite3.connect(self.path)
        else:
            if not self.path.exists(): raise FileNotFoundError(self.path)
            con=sqlite3.connect(f"file:{self.path}?mode=ro",uri=True)
        con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON"); con.execute("PRAGMA busy_timeout=5000")
        if write: con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            if write: con.commit()
        except Exception:
            if write: con.rollback()
            raise
        finally: con.close()

    def import_file(self,path: str|Path,*,label:str|None=None,search_note:str|None=None)->dict[str,Any]:
        source=Path(path); data=source.read_bytes(); text=data.decode("utf-8-sig")
        return self.import_text(text,source_filename=source.name,source_sha256=_sha256_bytes(data),label=label,search_note=search_note)

    def import_text(self,text:str,*,source_filename:str="<memory>",source_sha256:str|None=None,label:str|None=None,search_note:str|None=None)->dict[str,Any]:
        self.initialize(); records=parse_records(text)
        if not records: raise ValueError("no complete WoS records found in tagged plain-text input")
        digest=source_sha256 or _sha256_bytes(text.encode("utf-8")); imported_at=_now()
        with self.connect(write=True) as con:
            cur=con.execute("INSERT INTO wos_import_batches(source_filename,source_sha256,label,search_note,imported_at) VALUES(?,?,?,?,?)",(source_filename,digest,label,search_note,imported_at)); batch_id=int(cur.lastrowid)
            new_count=updated_count=0
            for record in records:
                existed=con.execute("SELECT 1 FROM wos_records WHERE ut=?",(record.ut,)).fetchone() is not None
                self._upsert_record(con,record,batch_id=batch_id,imported_at=imported_at)
                new_count+=int(not existed); updated_count+=int(existed)
            self.resolve_citation_targets(con)
            con.execute("UPDATE wos_import_batches SET record_count=?,new_count=?,updated_count=? WHERE batch_id=?",(len(records),new_count,updated_count,batch_id))
        return {"batch_id":batch_id,"source_filename":source_filename,"source_sha256":digest,"record_count":len(records),"new_count":new_count,"updated_count":updated_count}

    def _upsert_record(self,con:sqlite3.Connection,record:ParsedWosRecord,*,batch_id:int,imported_at:str)->None:
        old=con.execute("SELECT first_imported_at FROM wos_records WHERE ut=?",(record.ut,)).fetchone(); first=old[0] if old else imported_at
        con.execute("""INSERT INTO wos_records(ut,doi,normalized_doi,title,normalized_title,source_title,document_type,abstract,publication_year,publication_date,volume,issue,begin_page,end_page,article_number,pmid,times_cited_wos,times_cited_total,raw_record,first_imported_at,last_imported_at,last_batch_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ut) DO UPDATE SET doi=excluded.doi,normalized_doi=excluded.normalized_doi,title=excluded.title,normalized_title=excluded.normalized_title,source_title=excluded.source_title,document_type=excluded.document_type,abstract=excluded.abstract,publication_year=excluded.publication_year,publication_date=excluded.publication_date,volume=excluded.volume,issue=excluded.issue,begin_page=excluded.begin_page,end_page=excluded.end_page,article_number=excluded.article_number,pmid=excluded.pmid,times_cited_wos=excluded.times_cited_wos,times_cited_total=excluded.times_cited_total,raw_record=excluded.raw_record,last_imported_at=excluded.last_imported_at,last_batch_id=excluded.last_batch_id""",
        (record.ut,record.doi,normalize_doi(record.doi),record.title,record.normalized_title,record.source_title,record.document_type,record.abstract,record.publication_year,record.publication_date,record.volume,record.issue,record.begin_page,record.end_page,record.article_number,record.pmid,record.times_cited_wos,record.times_cited_total,record.raw_record.raw_text,first,imported_at,batch_id))
        con.execute("DELETE FROM wos_author_identifiers WHERE ut=?",(record.ut,))
        con.execute("DELETE FROM wos_addresses WHERE ut=?",(record.ut,)); con.execute("DELETE FROM wos_organizations WHERE ut=?",(record.ut,))
        con.execute("DELETE FROM wos_correspondence_groups WHERE ut=?",(record.ut,)); con.execute("DELETE FROM wos_emails WHERE ut=?",(record.ut,))
        con.execute("DELETE FROM wos_keywords WHERE ut=?",(record.ut,)); con.execute("DELETE FROM wos_classifications WHERE ut=?",(record.ut,))
        con.execute("DELETE FROM wos_funding WHERE ut=?",(record.ut,)); con.execute("DELETE FROM wos_cited_references WHERE source_ut=?",(record.ut,))
        con.execute("DELETE FROM wos_authors WHERE ut=?",(record.ut,))
        author_ids:dict[int,int]={}; au_map:dict[str,int]={}; full_map:dict[str,int]={}
        for a in record.authors:
            cur=con.execute("INSERT INTO wos_authors(ut,order_index,au_name,full_name,normalized_au,normalized_full_name) VALUES(?,?,?,?,?,?)",(record.ut,a.order_index,a.au_name,a.full_name,normalize_author_key(a.au_name),normalize_author_key(a.full_name))); aid=int(cur.lastrowid); author_ids[a.order_index]=aid
            if normalize_author_key(a.au_name): au_map[normalize_author_key(a.au_name)]=aid
            if normalize_author_key(a.full_name): full_map[normalize_author_key(a.full_name)]=aid
        def identifier_author_id(raw:str)->int|None:
            key=normalize_author_key(_identifier_name(raw))
            if not key:return None
            if key in full_map:return full_map[key]
            candidates=[]; tokens=key.split()
            for a in record.authors:
                fk=normalize_author_key(a.full_name)
                if fk and tokens and fk.split()[0]==tokens[0] and (len(tokens)==1 or any(t.startswith(tokens[-1]) or tokens[-1].startswith(t) for t in fk.split()[1:])): candidates.append(author_ids[a.order_index])
            return candidates[0] if len(set(candidates))==1 else None
        for ns,values in (("RESEARCHER_ID",record.researcher_ids),("ORCID",record.orcids)):
            for raw in values: con.execute("INSERT INTO wos_author_identifiers(wos_author_id,ut,namespace,value,raw_value) VALUES(?,?,?,?,?)",(identifier_author_id(raw),record.ut,ns,_identifier_value(raw),raw))
        for addr in record.addresses:
            cur=con.execute("INSERT INTO wos_addresses(ut,order_index,raw_address) VALUES(?,?,?)",(record.ut,addr.order_index,addr.address)); address_id=int(cur.lastrowid)
            for name in addr.author_names:
                aid=full_map.get(normalize_author_key(name) or "")
                if aid is not None: con.execute("INSERT OR IGNORE INTO wos_author_addresses(wos_author_id,address_id) VALUES(?,?)",(aid,address_id))
        for i,value in enumerate(record.organizations): con.execute("INSERT INTO wos_organizations(ut,order_index,organization) VALUES(?,?,?)",(record.ut,i,value))
        for group in record.correspondence_groups:
            cur=con.execute("INSERT INTO wos_correspondence_groups(ut,order_index,raw_group,raw_address) VALUES(?,?,?,?)",(record.ut,group.order_index,group.raw_group,group.address)); gid=int(cur.lastrowid)
            for name in group.member_names:
                key=normalize_author_key(name); con.execute("INSERT INTO wos_correspondence_members(correspondence_group_id,wos_author_id,raw_member_name,normalized_member_name) VALUES(?,?,?,?)",(gid,au_map.get(key or ""),name,key))
        for i,email in enumerate(record.emails): con.execute("INSERT INTO wos_emails(ut,order_index,email) VALUES(?,?,?)",(record.ut,i,email))
        for kind,values in (("AUTHOR",record.author_keywords),("KEYWORDS_PLUS",record.keywords_plus)):
            for i,value in enumerate(values): con.execute("INSERT INTO wos_keywords(ut,keyword_type,order_index,keyword) VALUES(?,?,?,?)",(record.ut,kind,i,value))
        for ns,values in record.classifications.items():
            for i,value in enumerate(values): con.execute("INSERT INTO wos_classifications(ut,namespace,order_index,value) VALUES(?,?,?,?)",(record.ut,ns,i,value))
        if record.funding_agencies or record.funding_text: con.execute("INSERT INTO wos_funding(ut,funding_agencies_raw,funding_text_raw) VALUES(?,?,?)",(record.ut,record.funding_agencies,record.funding_text))
        for ref in record.references: con.execute("INSERT INTO wos_cited_references(source_ut,order_index,raw_reference,cited_doi,cited_author,cited_year,cited_source,volume,page,target_ut) VALUES(?,?,?,?,?,?,?,?,?,NULL)",(record.ut,ref.order_index,ref.raw_text,ref.doi,ref.cited_author,ref.cited_year,ref.cited_source,ref.volume,ref.page))
        con.execute("INSERT OR REPLACE INTO wos_record_metrics(ut,batch_id,observed_at,times_cited_wos,times_cited_total) VALUES(?,?,?,?,?)",(record.ut,batch_id,imported_at,record.times_cited_wos,record.times_cited_total))

    @staticmethod
    def resolve_citation_targets(con:sqlite3.Connection)->int:
        con.execute("""UPDATE wos_cited_references SET target_ut=(SELECT r.ut FROM wos_records r WHERE r.normalized_doi=wos_cited_references.cited_doi ORDER BY r.ut LIMIT 1) WHERE cited_doi IS NOT NULL""")
        return int(con.execute("SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL").fetchone()[0])

    def stats(self)->dict[str,int]:
        with self.connect() as con:
            def q(sql:str)->int:return int(con.execute(sql).fetchone()[0])
            return {"records":q("SELECT count(*) FROM wos_records"),"authors":q("SELECT count(*) FROM wos_authors"),"corresponding_members":q("SELECT count(*) FROM wos_correspondence_members"),"cited_references":q("SELECT count(*) FROM wos_cited_references"),"resolved_citation_edges":q("SELECT count(*) FROM wos_cited_references WHERE target_ut IS NOT NULL"),"import_batches":q("SELECT count(*) FROM wos_import_batches")}

    def find_by_doi(self,doi:str)->list[dict[str,Any]]:
        value=normalize_doi(doi)
        if not value:return []
        with self.connect() as con:return [dict(r) for r in con.execute("SELECT * FROM wos_records WHERE normalized_doi=? ORDER BY ut",(value,)).fetchall()]

    def find_by_exact_title(self,title:str)->list[dict[str,Any]]:
        value=normalize_title(title)
        if not value:return []
        with self.connect() as con:return [dict(r) for r in con.execute("SELECT * FROM wos_records WHERE normalized_title=? ORDER BY publication_year,ut",(value,)).fetchall()]

    def search(self,query:str,*,limit:int=50)->list[dict[str,Any]]:
        q=query.strip().casefold()
        if not q:return []
        like=f"%{q}%"
        with self.connect() as con:
            rows=con.execute("""SELECT DISTINCT r.* FROM wos_records r LEFT JOIN wos_authors a ON a.ut=r.ut LEFT JOIN wos_keywords k ON k.ut=r.ut WHERE lower(coalesce(r.title,'')) LIKE ? OR lower(coalesce(r.doi,'')) LIKE ? OR lower(coalesce(r.ut,'')) LIKE ? OR lower(coalesce(r.source_title,'')) LIKE ? OR lower(coalesce(a.full_name,a.au_name,'')) LIKE ? OR lower(coalesce(k.keyword,'')) LIKE ? ORDER BY r.publication_year DESC,r.ut LIMIT ?""",(like,like,like,like,like,like,max(1,min(limit,500)))).fetchall(); return [dict(r) for r in rows]

    def get_record(self,ut:str)->dict[str,Any]|None:
        with self.connect() as con:
            row=con.execute("SELECT * FROM wos_records WHERE ut=?",(ut,)).fetchone()
            if row is None:return None
            result=dict(row); authors=[dict(r) for r in con.execute("SELECT * FROM wos_authors WHERE ut=? ORDER BY order_index",(ut,)).fetchall()]; groups=[]
            for g in con.execute("SELECT * FROM wos_correspondence_groups WHERE ut=? ORDER BY order_index",(ut,)).fetchall():
                members=[dict(x) for x in con.execute("SELECT m.*,a.au_name,a.full_name FROM wos_correspondence_members m LEFT JOIN wos_authors a ON a.wos_author_id=m.wos_author_id WHERE m.correspondence_group_id=? ORDER BY m.rowid",(g['correspondence_group_id'],)).fetchall()]; groups.append({**dict(g),"members":members})
            funding=con.execute("SELECT * FROM wos_funding WHERE ut=?",(ut,)).fetchone()
            result.update(authors=authors,correspondence_groups=groups,emails=[r['email'] for r in con.execute("SELECT email FROM wos_emails WHERE ut=? ORDER BY order_index",(ut,)).fetchall()],keywords=[dict(r) for r in con.execute("SELECT keyword_type,keyword FROM wos_keywords WHERE ut=? ORDER BY keyword_type,order_index",(ut,)).fetchall()],classifications=[dict(r) for r in con.execute("SELECT namespace,value FROM wos_classifications WHERE ut=? ORDER BY namespace,order_index",(ut,)).fetchall()],organizations=[r['organization'] for r in con.execute("SELECT organization FROM wos_organizations WHERE ut=? ORDER BY order_index",(ut,)).fetchall()],funding=dict(funding) if funding else {},reference_count=int(con.execute("SELECT count(*) FROM wos_cited_references WHERE source_ut=?",(ut,)).fetchone()[0]),resolved_reference_count=int(con.execute("SELECT count(*) FROM wos_cited_references WHERE source_ut=? AND target_ut IS NOT NULL",(ut,)).fetchone()[0]))
            return result

    def list_references(self,ut:str,*,limit:int=500,offset:int=0)->list[dict[str,Any]]:
        with self.connect() as con:return [dict(r) for r in con.execute("SELECT * FROM wos_cited_references WHERE source_ut=? ORDER BY order_index LIMIT ? OFFSET ?",(ut,max(1,min(limit,2000)),max(0,offset))).fetchall()]

    def citation_frontier(self,*,limit:int=100)->list[dict[str,Any]]:
        with self.connect() as con:
            rows=con.execute("""SELECT cited_doi,count(*) AS cited_by_count,min(cited_author) AS cited_author,min(cited_year) AS cited_year,min(cited_source) AS cited_source FROM wos_cited_references WHERE cited_doi IS NOT NULL AND target_ut IS NULL GROUP BY cited_doi ORDER BY cited_by_count DESC,cited_doi LIMIT ?""",(max(1,min(limit,1000)),)).fetchall(); return [dict(r) for r in rows]
