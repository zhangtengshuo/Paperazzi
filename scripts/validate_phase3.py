#!/usr/bin/env python3
"""Phase 3D — real-library persistence validation (thin operational script).

Creates a fresh ignored Paperazzi DB, imports the full active Zotero canonical
library twice, persists a deterministic 200-PDF extraction sample, and reports
idempotency/rollback evidence per PHASE3_IMPLEMENTATION.md §3D.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sqlalchemy as sa  # noqa: E402

from paperazzi.database.engine import create_paperazzi_engine  # noqa: E402
from paperazzi.database.models import (  # noqa: E402
    DocumentEvidenceSpan,
    DocumentExtractionAttempt,
    DocumentExtractionRun,
    Paper,
    PaperCreatorMention,
    PaperDocument,
    PaperReference,
    PaperReferenceIdentifier,
    PaperReferenceSection,
    ZoteroAttachment,
    ZoteroItemState,
    ZoteroItemVersion,
    ZoteroScanRun,
)
from paperazzi.database.persistence import persist_zotero_scan  # noqa: E402
from paperazzi.database.repositories import (  # noqa: E402
    EXTRACTOR_VERSION,
    PROMPT_HASH,
    PROMPT_VERSION,
    accept_attempt,
    add_extraction_attempt,
    create_extraction_run,
    decide_extraction_trigger,
    persist_evidence_spans,
    persist_reference_section,
)
from paperazzi.ingest.models import CanonicalZoteroItem  # noqa: E402
from paperazzi.local_evidence.pdf import extract_pdf_evidence  # noqa: E402
from paperazzi.zotero_sqlite.probe import create_snapshot, open_readonly  # noqa: E402
from paperazzi.zotero_sqlite.reader import ZoteroSQLiteReader  # noqa: E402

ZOTERO_DB = Path("/mnt/d/zotero/zotero.sqlite")
ZOTERO_DATA = Path("/mnt/d/zotero")
RUN_DIR = REPO_ROOT / "data" / "phase3-validation"
DB_PATH = RUN_DIR / "paperazzi.sqlite3"
SNAPSHOT = RUN_DIR / "zotero_snapshot.sqlite"
V3_REPORT = REPO_ROOT / "pdf-evidence-output/20260817-022324-pdf-evidence-v3/pdf_evidence_report.json"


def read_canonical(snapshot: Path) -> list[CanonicalZoteroItem]:
    conn = sqlite3.connect(f"file:{snapshot.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        reader = ZoteroSQLiteReader(conn, ZOTERO_DATA)
        return list(reader.iter_items())
    finally:
        conn.close()


def report_scan(session_factory, items: list[CanonicalZoteroItem], token: str):
    result = persist_zotero_scan(
        session_factory,
        items,
        {
            "run_token": token,
            "source_db_path": str(ZOTERO_DB),
            "source_db_size": ZOTERO_DB.stat().st_size,
            "snapshot_path": str(SNAPSHOT),
            "adapter_name": "userdata125-global42",
            "userdata_version": 125,
            "global_schema_version": 42,
        },
    )
    assert result.status == "COMPLETED", result.error
    return result.counts


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    for p in (DB_PATH, Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm"), SNAPSHOT):
        p.unlink(missing_ok=True)

    env = dict(__import__("os").environ)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{DB_PATH}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, env=env, check=True,
    )
    migration_head = subprocess.run(
        [sys.executable, "-m", "alembic", "current"], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()[-1].strip()

    engine = create_paperazzi_engine(DB_PATH)
    session_factory = sa.orm.sessionmaker(bind=engine)

    # ---- 快照 + 全量扫描 x2 ----
    source = open_readonly(ZOTERO_DB)
    create_snapshot(source, SNAPSHOT)
    source.close()

    items1 = read_canonical(SNAPSHOT)
    first = report_scan(session_factory, items1, "real-full-1")
    items2 = read_canonical(SNAPSHOT)
    assert len(items2) == len(items1)
    second = report_scan(session_factory, items2, "real-full-2")

    with session_factory() as s:
        fk_rows = s.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        counts = {
            "full_zotero_item_count": s.query(ZoteroItemState).count(),
            "paper_count": s.query(Paper).count(),
            "creator_mention_count": s.query(PaperCreatorMention).count(),
            "pdf_document_count": s.query(PaperDocument).count(),
            "local_pdf_available_count": s.query(PaperDocument).filter_by(
                availability_status="PDF_AVAILABLE").count(),
            "item_version_rows_after_first_scan": s.query(ZoteroItemVersion).count(),
            "attachment_count": s.query(ZoteroAttachment).count(),
        }
        dup = s.execute(sa.text(
            "SELECT library_id, item_key, COUNT(*) FROM zotero_item_state "
            "GROUP BY library_id, item_key HAVING COUNT(*) > 1")).fetchall()
        counts["duplicate_identities"] = len(dup)

    # ---- 200-PDF 抽取样本 ----
    v3 = json.load(open(V3_REPORT))
    sample_keys = [d["attachment_key"] for d in v3["samples"]][:200]
    runs_created = attempts = spans = sections = refs = identifiers = 0
    anchor_state = {}
    with session_factory() as s:
        for idx, att_key in enumerate(sample_keys):
            att = s.query(ZoteroAttachment).filter_by(
                library_id=1, item_key=att_key).one_or_none()
            if att is None:
                continue
            document = s.query(PaperDocument).filter_by(
                zotero_attachment_id=att.zotero_attachment_id).one_or_none()
            if document is None or document.availability_status != "PDF_AVAILABLE":
                continue
            path = document.local_path
            if not path or not Path(path).is_file():
                continue
            trigger = decide_extraction_trigger(document, document.document_change_key,
                                                EXTRACTOR_VERSION, PROMPT_HASH)
            if trigger is None:
                continue
            run = create_extraction_run(s, document.document_id, trigger,
                                        document.document_change_key)
            runs_created += 1
            try:
                evidence = extract_pdf_evidence(path)
            except Exception as exc:  # noqa: BLE001
                run.status = "FAILED"
                run.error_message = str(exc)[:500]
                s.flush()
                continue
            status = evidence.text_status
            decision = "PASS" if status == "NATIVE_TEXT_GOOD" else "ACCEPT_PARTIAL"
            if status in ("NO_TEXT_LAYER", "THIN_TEXT_LAYER", "NATIVE_TEXT_SPARSE"):
                decision = "NEEDS_OCR" if status == "NO_TEXT_LAYER" else "ACCEPT_PARTIAL"
            attempt = add_extraction_attempt(
                s, run, attempt_number=1, actor="DETERMINISTIC",
                strategy="deterministic-v3", text_source="PDF_NATIVE",
                decision=decision, backend="PyMuPDF",
                backend_version=evidence.backend_version,
                text_channel=(
                    evidence.references.text_channel if evidence.references else None),
                channels_evaluated=["PYMUPDF_SORTED", "PYMUPDF_CONTENT_STREAM"],
                section_confidence=(
                    evidence.references.confidence if evidence.references else None),
                segmentation_confidence=(
                    evidence.references.confidence if evidence.references else None),
                entry_text_quality=(
                    "GOOD" if evidence.text_status == "NATIVE_TEXT_GOOD" else "PARTIAL"),
                reference_status=(
                    "SEGMENTED" if evidence.references and evidence.references.entries
                    else ("RAW_SECTION_ONLY" if evidence.references else "NO_REFERENCE_SECTION_FOUND")),
            )
            attempts += 1
            spans += persist_evidence_spans(
                s, document.document_id, attempt,
                [
                    {"kind": "affiliation", "page_index": sp.page_index, "text": sp.text}
                    for sp in evidence.affiliation_candidates[:4]
                ] + [
                    {"kind": "correspondence", "page_index": sp.page_index, "text": sp.text}
                    for sp in evidence.correspondence_candidates[:2]
                ],
                text_source="PDF_NATIVE",
                text_channel="PYMUPDF_SORTED",
            )
            if evidence.references is not None:
                persist_reference_section(
                    s, document.paper_id, document.document_id, attempt,
                    evidence.references,
                )
                sections += 1
                refs += len(evidence.references.entries)
                identifiers += sum(
                    len(e.dois) + len(e.years) for e in evidence.references.entries
                )
            final = "PASS" if decision == "PASS" else (
                "NEEDS_OCR" if decision == "NEEDS_OCR" else "ACCEPT_PARTIAL")
            accept_attempt(s, run, attempt, final)
            if att_key in anchor_state:
                anchor_state[att_key] = {
                    "method": evidence.references.method if evidence.references else None,
                    "entries": len(evidence.references.entries) if evidence.references else None,
                }
            if idx % 50 == 0:
                s.commit()
        s.commit()

    # 幂等: 第二次同样抽取调用 decide 应无新 run
    with session_factory() as s:
        rerun = 0
        for att_key in sample_keys[:20]:
            att = s.query(ZoteroAttachment).filter_by(library_id=1, item_key=att_key).one_or_none()
            if att is None:
                continue
            document = s.query(PaperDocument).filter_by(
                zotero_attachment_id=att.zotero_attachment_id).one_or_none()
            if document is None:
                continue
            if decide_extraction_trigger(document, document.document_change_key,
                                         EXTRACTOR_VERSION, PROMPT_HASH) is not None:
                rerun += 1
        idempotency = "OK-no-duplicate-runs" if rerun == 0 else f"RE-RUN-{rerun}"

    # 失败注入(临时库)
    tmp_db = RUN_DIR / "injection.sqlite3"
    for p in (tmp_db, Path(str(tmp_db) + "-wal"), Path(str(tmp_db) + "-shm")):
        p.unlink(missing_ok=True)
    env["PAPERAZZI_DB_URL"] = f"sqlite:///{tmp_db}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=REPO_ROOT, env=env, check=True)
    tmp_engine = create_paperazzi_engine(tmp_db)
    tmp_sf = sa.orm.sessionmaker(bind=tmp_engine)
    injected = persist_zotero_scan(
        tmp_sf,
        [items1[0], items1[0]],  # 重复身份 -> 失败
        {"run_token": "inject-1", "source_db_path": str(ZOTERO_DB)},
    )
    with tmp_sf() as s:
        run_row = s.query(ZoteroScanRun).filter_by(run_token="inject-1").one()
        rollback_injection = {
            "scan_status": injected.status,
            "run_row_status": run_row.status,
            "papers_rows": s.query(Paper).count(),
        }
    tmp_engine.dispose()

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "phase": "3D",
        "migration_head": migration_head,
        "first_scan": first,
        "second_scan": second,
        "counts": counts,
        "fk_check_rows": len(fk_rows),
        "pdf_sample": {
            "sample_size": len(sample_keys),
            "extraction_runs_created": runs_created,
            "attempt_count": attempts,
            "evidence_span_count": spans,
            "reference_section_count": sections,
            "reference_entry_count": refs,
            "reference_identifier_count": identifiers,
            "anchors": {k: v for k, v in anchor_state.items()},
        },
        "idempotency_result": idempotency,
        "rollback_injection_result": rollback_injection,
    }
    report_path = RUN_DIR / "phase3_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
