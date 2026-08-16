"""Phase 3B/3.1 — Zotero scan/diff persistence service.

Consumes validated ``CanonicalZoteroItem`` records and persists one scan
atomically. Never executes Zotero-specific SQL here; the caller supplies
canonical records produced by the validated reader.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperazzi.ingest.models import CanonicalZoteroItem

from .base import utcnow
from .models import (
    Paper,
    PaperCreatorMention,
    PaperDocument,
    ZoteroAttachment,
    ZoteroItemCollection,
    ZoteroItemState,
    ZoteroItemTag,
    ZoteroItemVersion,
    ZoteroScanRun,
)

CHANGE_NEW = "NEW"
CHANGE_MODIFIED = "MODIFIED"
CHANGE_UNCHANGED = "UNCHANGED"
CHANGE_REMOVED = "REMOVED"
CHANGE_RESTORED = "RESTORED"

DIM_BIBLIOGRAPHIC = "BIBLIOGRAPHIC"
DIM_ORGANIZATION = "ORGANIZATION"
DIM_ATTACHMENT = "ATTACHMENT"

PDF_CONTENT_TYPE = "application/pdf"


@dataclass(frozen=True)
class ItemChange:
    identity: str
    change_type: str
    changed_dimensions: frozenset[str] = field(default_factory=frozenset)
    previous_hashes: dict[str, str | None] = field(default_factory=dict)
    current_hashes: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanResult:
    scan_run_id: int
    status: str
    counts: dict[str, int] = field(default_factory=dict)
    changes: tuple[ItemChange, ...] = ()
    error: str | None = None


def _canonical_json(item: CanonicalZoteroItem) -> str:
    return json.dumps(item.stable_payload(), ensure_ascii=False, sort_keys=True)


def _corpus_hash(items: Iterable[CanonicalZoteroItem], key: str) -> str:
    digests = sorted(getattr(item, key)() for item in items)
    return hashlib.sha256(
        json.dumps(digests, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class ScanPersistenceError(RuntimeError):
    pass


def persist_zotero_scan(
    session_factory: Any,
    canonical_items: Sequence[CanonicalZoteroItem],
    scan_metadata: dict[str, Any],
) -> ScanResult:
    """Persist one full active-library scan atomically."""
    run_token = scan_metadata.get("run_token")
    if not run_token:
        raise ScanPersistenceError("scan_metadata requires run_token")

    session = session_factory()
    try:
        run = ZoteroScanRun(
            run_token=run_token,
            status="STARTED",
            source_db_path=scan_metadata["source_db_path"],
            source_db_size=scan_metadata.get("source_db_size"),
            source_db_mtime_ns=scan_metadata.get("source_db_mtime_ns"),
            snapshot_path=scan_metadata.get("snapshot_path"),
            adapter_name=scan_metadata.get("adapter_name"),
            userdata_version=scan_metadata.get("userdata_version"),
            global_schema_version=scan_metadata.get("global_schema_version"),
            started_at=utcnow(),
        )
        session.add(run)
        session.flush()
        run_id = run.scan_run_id
        session.commit()

        try:
            result = _apply_scan(session, run_id, canonical_items)
            run = session.get(ZoteroScanRun, run_id)
            run.status = "COMPLETED"
            run.item_count = len(canonical_items)
            run.new_count = result["counts"].get(CHANGE_NEW, 0)
            run.modified_count = result["counts"].get(CHANGE_MODIFIED, 0)
            run.unchanged_count = result["counts"].get(CHANGE_UNCHANGED, 0)
            run.removed_count = result["counts"].get(CHANGE_REMOVED, 0)
            run.restored_count = result["counts"].get(CHANGE_RESTORED, 0)
            run.bibliographic_corpus_hash = _corpus_hash(canonical_items, "bibliographic_hash")
            run.canonical_corpus_hash = _corpus_hash(canonical_items, "canonical_hash")
            run.completed_at = utcnow()
            session.commit()
            return ScanResult(
                scan_run_id=run_id,
                status="COMPLETED",
                counts=result["counts"],
                changes=result["changes"],
            )
        except Exception as exc:
            session.rollback()
            run = session.get(ZoteroScanRun, run_id)
            run.status = "FAILED"
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:2000]
            run.completed_at = utcnow()
            session.commit()
            return ScanResult(scan_run_id=run_id, status="FAILED", error=str(exc))
    finally:
        session.close()


def _apply_scan(
    session: Any,
    run_id: int,
    items: Sequence[CanonicalZoteroItem],
) -> dict[str, Any]:
    counts = {
        k: 0
        for k in (
            CHANGE_NEW,
            CHANGE_MODIFIED,
            CHANGE_UNCHANGED,
            CHANGE_REMOVED,
            CHANGE_RESTORED,
        )
    }
    changes: list[ItemChange] = []
    states = {
        (state.library_id, state.item_key): state
        for state in session.query(ZoteroItemState).all()
    }
    seen_identities: set[tuple[int, str]] = set()

    for item in items:
        identity = (item.library_id, item.item_key)
        if identity in seen_identities:
            raise ScanPersistenceError(
                f"duplicate identity in scan input: {item.zotero_identity}"
            )
        seen_identities.add(identity)

        b_hash = item.bibliographic_hash()
        o_hash = item.organization_hash()
        a_hash = item.attachment_hash()
        c_hash = item.canonical_hash()
        current = {
            "bibliographic_hash": b_hash,
            "organization_hash": o_hash,
            "attachment_hash": a_hash,
            "canonical_hash": c_hash,
        }

        prior = states.get(identity)
        if prior is None:
            change_type = CHANGE_NEW
            dimensions: frozenset[str] = frozenset(
                (DIM_BIBLIOGRAPHIC, DIM_ORGANIZATION, DIM_ATTACHMENT)
            )
        elif not prior.present_in_last_scan:
            change_type = CHANGE_RESTORED
            dimensions = _dimensions(prior, current)
        elif prior.canonical_hash != c_hash:
            change_type = CHANGE_MODIFIED
            dimensions = _dimensions(prior, current)
        else:
            change_type = CHANGE_UNCHANGED
            dimensions = frozenset()

        counts[change_type] += 1
        changes.append(
            ItemChange(
                identity=item.zotero_identity,
                change_type=change_type,
                changed_dimensions=dimensions,
                previous_hashes={
                    key: getattr(prior, key) if prior is not None else None
                    for key in (
                        "bibliographic_hash",
                        "organization_hash",
                        "attachment_hash",
                        "canonical_hash",
                    )
                },
                current_hashes=current,
            )
        )

        if change_type == CHANGE_UNCHANGED:
            # Local file availability is intentionally outside semantic hashes. It
            # still has to refresh every scan so a newly downloaded PDF becomes
            # PDF_AVAILABLE and can trigger FIRST_AVAILABLE extraction.
            prior.zotero_version = item.zotero_version
            prior.date_modified = item.date_modified
            prior.client_date_modified = item.client_date_modified
            prior.last_seen_run_id = run_id
            prior.updated_at = utcnow()
            _refresh_attachment_runtime_state(
                session, prior.paper_id, prior, item, run_id
            )
            continue

        if prior is None:
            paper = Paper(
                title=item.title,
                doi=item.doi,
                publication_year=_publication_year(item.fields),
                publication_date_text=item.fields.get("date"),
                venue=_venue(item.fields),
                item_type=item.item_type,
                active_in_zotero=True,
            )
            session.add(paper)
            session.flush()
            state = ZoteroItemState(
                paper_id=paper.paper_id,
                library_id=item.library_id,
                item_key=item.item_key,
                zotero_item_id=item.item_id,
                item_type=item.item_type,
                zotero_version=item.zotero_version,
                date_added=item.date_added,
                date_modified=item.date_modified,
                client_date_modified=item.client_date_modified,
                deleted=item.deleted,
                present_in_last_scan=True,
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                bibliographic_hash=b_hash,
                organization_hash=o_hash,
                attachment_hash=a_hash,
                canonical_hash=c_hash,
                canonical_payload_json=_canonical_json(item),
            )
            session.add(state)
            session.flush()
            _reconcile_mentions(session, paper.paper_id, state.zotero_item_state_id, item)
            _replace_tags(session, state.zotero_item_state_id, item)
            _replace_collections(session, state.zotero_item_state_id, item)
            _replace_attachments(session, paper.paper_id, state, item, run_id)
        else:
            state = prior
            paper = session.get(Paper, state.paper_id)
            if paper is None:
                raise ScanPersistenceError(
                    f"missing paper_id={state.paper_id} for {item.zotero_identity}"
                )

            paper.active_in_zotero = True
            paper.updated_at = utcnow()
            state.item_type = item.item_type
            state.zotero_version = item.zotero_version
            state.date_added = item.date_added
            state.date_modified = item.date_modified
            state.client_date_modified = item.client_date_modified
            state.deleted = item.deleted
            state.present_in_last_scan = True
            state.last_seen_run_id = run_id
            state.bibliographic_hash = b_hash
            state.organization_hash = o_hash
            state.attachment_hash = a_hash
            state.canonical_hash = c_hash
            state.canonical_payload_json = _canonical_json(item)
            state.updated_at = utcnow()

            if DIM_BIBLIOGRAPHIC in dimensions:
                paper.title = item.title
                paper.doi = item.doi
                paper.publication_year = _publication_year(item.fields)
                paper.publication_date_text = item.fields.get("date")
                paper.venue = _venue(item.fields)
                paper.item_type = item.item_type
                _reconcile_mentions(
                    session, paper.paper_id, state.zotero_item_state_id, item
                )

            if DIM_ORGANIZATION in dimensions:
                session.query(ZoteroItemTag).filter_by(
                    zotero_item_state_id=state.zotero_item_state_id
                ).delete()
                session.query(ZoteroItemCollection).filter_by(
                    zotero_item_state_id=state.zotero_item_state_id
                ).delete()
                _replace_tags(session, state.zotero_item_state_id, item)
                _replace_collections(session, state.zotero_item_state_id, item)

            # RESTORED must reactivate child presence even if the semantic
            # attachment hash is unchanged from before removal.
            if DIM_ATTACHMENT in dimensions or change_type == CHANGE_RESTORED:
                _replace_attachments(session, paper.paper_id, state, item, run_id)
            else:
                _refresh_attachment_runtime_state(
                    session, paper.paper_id, state, item, run_id
                )

        session.add(
            ZoteroItemVersion(
                zotero_item_state_id=state.zotero_item_state_id,
                scan_run_id=run_id,
                change_type=change_type,
                changed_dimensions_json=json.dumps(sorted(dimensions)),
                bibliographic_hash=b_hash,
                organization_hash=o_hash,
                attachment_hash=a_hash,
                canonical_hash=c_hash,
                canonical_payload_json=_canonical_json(item),
            )
        )

    for (lib_id, key), prior in states.items():
        if (lib_id, key) not in seen_identities and prior.present_in_last_scan:
            counts[CHANGE_REMOVED] += 1
            prior.present_in_last_scan = False
            prior.last_seen_run_id = run_id
            prior.updated_at = utcnow()
            paper = session.get(Paper, prior.paper_id)
            if paper is not None:
                paper.active_in_zotero = False
                paper.updated_at = utcnow()
            _mark_parent_attachments_removed(session, prior, run_id)
            session.add(
                ZoteroItemVersion(
                    zotero_item_state_id=prior.zotero_item_state_id,
                    scan_run_id=run_id,
                    change_type=CHANGE_REMOVED,
                    changed_dimensions_json="[]",
                    bibliographic_hash=prior.bibliographic_hash,
                    organization_hash=prior.organization_hash,
                    attachment_hash=prior.attachment_hash,
                    canonical_hash=prior.canonical_hash,
                    canonical_payload_json=prior.canonical_payload_json,
                )
            )
            changes.append(
                ItemChange(
                    identity=f"zotero:{lib_id}:{key}",
                    change_type=CHANGE_REMOVED,
                    previous_hashes={"canonical_hash": prior.canonical_hash},
                    current_hashes={"canonical_hash": None},
                )
            )

    return {"counts": counts, "changes": changes}


def _dimensions(prior: Any, current: dict[str, str]) -> frozenset[str]:
    dims: set[str] = set()
    if prior.bibliographic_hash != current["bibliographic_hash"]:
        dims.add(DIM_BIBLIOGRAPHIC)
    if prior.organization_hash != current["organization_hash"]:
        dims.add(DIM_ORGANIZATION)
    if prior.attachment_hash != current["attachment_hash"]:
        dims.add(DIM_ATTACHMENT)
    return frozenset(dims)


def _publication_year(fields: dict[str, Any]) -> int | None:
    value = fields.get("date")
    if not value:
        return None
    match = __import__("re").search(r"(?:19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


def _venue(fields: dict[str, Any]) -> str | None:
    return fields.get("publicationTitle") or fields.get("journalAbbreviation")


def _reconcile_mentions(
    session: Any, paper_id: int, state_id: int, item: CanonicalZoteroItem
) -> None:
    """Update creator mentions in place, preserving IDs for persistent order slots."""
    existing = {
        mention.order_index: mention
        for mention in session.query(PaperCreatorMention)
        .filter_by(zotero_item_state_id=state_id)
        .all()
    }
    seen: set[int] = set()
    for creator in item.creators:
        seen.add(creator.order_index)
        display_name = (
            " ".join(
                part
                for part in (creator.first_name or "", creator.last_name or "")
                if part
            )
            or None
        )
        mention = existing.get(creator.order_index)
        if mention is None:
            session.add(
                PaperCreatorMention(
                    paper_id=paper_id,
                    zotero_item_state_id=state_id,
                    source_creator_id=creator.creator_id,
                    creator_type=creator.creator_type,
                    order_index=creator.order_index,
                    first_name=creator.first_name,
                    last_name=creator.last_name,
                    field_mode=creator.field_mode,
                    display_name=display_name,
                )
            )
        else:
            mention.paper_id = paper_id
            mention.source_creator_id = creator.creator_id
            mention.creator_type = creator.creator_type
            mention.first_name = creator.first_name
            mention.last_name = creator.last_name
            mention.field_mode = creator.field_mode
            mention.display_name = display_name
            mention.updated_at = utcnow()

    for order_index, mention in existing.items():
        if order_index not in seen:
            session.delete(mention)


def _replace_tags(session: Any, state_id: int, item: CanonicalZoteroItem) -> None:
    for tag in item.tags:
        session.add(
            ZoteroItemTag(
                zotero_item_state_id=state_id,
                tag_id=tag.tag_id,
                tag_type=tag.tag_type,
                name=tag.name,
            )
        )


def _replace_collections(session: Any, state_id: int, item: CanonicalZoteroItem) -> None:
    for collection in item.collections:
        session.add(
            ZoteroItemCollection(
                zotero_item_state_id=state_id,
                collection_id=collection.collection_id,
                collection_key=collection.collection_key,
                name=collection.name,
                parent_collection_id=collection.parent_collection_id,
                parent_collection_key=collection.parent_collection_key,
                order_index=collection.order_index,
            )
        )


def _replace_attachments(
    session: Any,
    paper_id: int,
    state: ZoteroItemState,
    item: CanonicalZoteroItem,
    run_id: int,
) -> None:
    """Upsert all Zotero attachments; create PaperDocument only for PDFs."""
    existing = {
        (row.library_id, row.item_key): row
        for row in session.query(ZoteroAttachment)
        .filter_by(zotero_item_state_id=state.zotero_item_state_id)
        .all()
    }
    seen: set[tuple[int, str]] = set()
    for att in item.attachments:
        identity = (att.library_id, att.item_key)
        seen.add(identity)
        row = existing.get(identity)
        if row is None:
            row = ZoteroAttachment(
                paper_id=paper_id,
                zotero_item_state_id=state.zotero_item_state_id,
                library_id=att.library_id,
                item_key=att.item_key,
                zotero_item_id=att.item_id,
                parent_item_id=att.parent_item_id,
                link_mode=att.link_mode,
                link_mode_name=att.link_mode_name,
                content_type=att.content_type,
                stored_path=att.path,
                resolved_path=att.resolved_path,
                resolution=att.resolution,
                local_exists=att.local_exists,
                storage_hash=att.storage_hash,
                storage_mod_time=att.storage_mod_time,
                present_in_last_scan=True,
                last_seen_run_id=run_id,
            )
            session.add(row)
            session.flush()
        else:
            _update_attachment_row(row, paper_id, att, run_id)

        if _is_pdf(att):
            _upsert_document(session, paper_id, row, att, run_id)
        else:
            document = (
                session.query(PaperDocument)
                .filter_by(zotero_attachment_id=row.zotero_attachment_id)
                .one_or_none()
            )
            if document is not None:
                document.present_in_last_scan = False
                document.availability_status = "FILE_UNAVAILABLE"
                document.last_seen_run_id = run_id
                document.updated_at = utcnow()

    for identity, row in existing.items():
        if identity not in seen:
            _mark_attachment_removed(session, row, run_id)


def _refresh_attachment_runtime_state(
    session: Any,
    paper_id: int,
    state: ZoteroItemState,
    item: CanonicalZoteroItem,
    run_id: int,
) -> None:
    """Refresh local-file state without creating a semantic Zotero MODIFIED."""
    existing = {
        (row.library_id, row.item_key): row
        for row in session.query(ZoteroAttachment)
        .filter_by(zotero_item_state_id=state.zotero_item_state_id)
        .all()
    }
    for att in item.attachments:
        row = existing.get((att.library_id, att.item_key))
        if row is None:
            _replace_attachments(session, paper_id, state, item, run_id)
            return
        _update_attachment_row(row, paper_id, att, run_id)
        if _is_pdf(att):
            _upsert_document(session, paper_id, row, att, run_id)


def _update_attachment_row(
    row: ZoteroAttachment, paper_id: int, att: Any, run_id: int
) -> None:
    row.paper_id = paper_id
    row.link_mode = att.link_mode
    row.link_mode_name = att.link_mode_name
    row.content_type = att.content_type
    row.stored_path = att.path
    row.resolved_path = att.resolved_path
    row.resolution = att.resolution
    row.local_exists = att.local_exists
    row.storage_hash = att.storage_hash
    row.storage_mod_time = att.storage_mod_time
    row.present_in_last_scan = True
    row.last_seen_run_id = run_id
    row.updated_at = utcnow()


def _mark_parent_attachments_removed(
    session: Any, state: ZoteroItemState, run_id: int
) -> None:
    for row in (
        session.query(ZoteroAttachment)
        .filter_by(zotero_item_state_id=state.zotero_item_state_id)
        .all()
    ):
        _mark_attachment_removed(session, row, run_id)


def _mark_attachment_removed(
    session: Any, row: ZoteroAttachment, run_id: int
) -> None:
    row.present_in_last_scan = False
    row.last_seen_run_id = run_id
    row.updated_at = utcnow()
    document = (
        session.query(PaperDocument)
        .filter_by(zotero_attachment_id=row.zotero_attachment_id)
        .one_or_none()
    )
    if document is not None:
        document.present_in_last_scan = False
        document.last_seen_run_id = run_id
        document.updated_at = utcnow()


def _is_pdf(att: Any) -> bool:
    return (att.content_type or "").lower() == PDF_CONTENT_TYPE


def _runtime_file_state(att: Any) -> tuple[int | None, int | None]:
    if not att.local_exists or not att.resolved_path:
        return None, None
    try:
        stat = Path(att.resolved_path).stat()
    except OSError:
        return None, None
    return int(stat.st_size), int(stat.st_mtime_ns)


def _upsert_document(
    session: Any,
    paper_id: int,
    attachment: ZoteroAttachment,
    att: Any,
    run_id: int,
) -> None:
    file_size, file_mtime_ns = _runtime_file_state(att)
    local_path = (
        att.resolved_path
        if att.resolution in ("zotero-storage", "linked-absolute-path")
        else None
    )
    document = (
        session.query(PaperDocument)
        .filter_by(zotero_attachment_id=attachment.zotero_attachment_id)
        .one_or_none()
    )
    values = {
        "paper_id": paper_id,
        "content_type": att.content_type,
        "local_path": local_path,
        "availability_status": _availability(att),
        "file_size": file_size,
        "file_mtime_ns": file_mtime_ns,
        "zotero_storage_hash": att.storage_hash,
        "document_change_key": _change_key(att, file_size, file_mtime_ns),
        "present_in_last_scan": True,
        "last_seen_run_id": run_id,
    }
    if document is None:
        document = PaperDocument(
            zotero_attachment_id=attachment.zotero_attachment_id,
            first_seen_run_id=run_id,
            **values,
        )
        session.add(document)
    else:
        for key, value in values.items():
            setattr(document, key, value)
        document.updated_at = utcnow()


def _availability(att: Any) -> str:
    if att.resolution in ("zotero-storage", "linked-absolute-path"):
        return "PDF_AVAILABLE" if att.local_exists else "PDF_RECORD_ONLY"
    if att.resolution in (
        "linked-base-directory-required",
        "linked-relative-path-unresolved",
        "linked-windows-path-unmapped",
    ):
        return "UNRESOLVED_PATH"
    return "FILE_UNAVAILABLE"


def _change_key(
    att: Any, file_size: int | None, file_mtime_ns: int | None
) -> str | None:
    if att.storage_hash:
        return f"zotero:{att.storage_hash}"
    if att.local_exists and file_size is not None and file_mtime_ns is not None:
        return f"fs:{file_size}:{file_mtime_ns}"
    return None
