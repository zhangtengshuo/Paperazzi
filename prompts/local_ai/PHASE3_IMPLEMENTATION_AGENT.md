# Paperazzi Local AI Prompt — Phase 3 Persistence Implementation

You are implementing and validating **Phase 3** of Paperazzi in the repository. This is a software-development task, not a free-form database redesign.

## 1. Read these first

Before changing code, read in this order:

```text
DESIGN.md
docs/architecture/ZOTERO_DATA_BOUNDARY.md
docs/architecture/LOCAL_PDF_EVIDENCE.md
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
docs/architecture/PERSISTENCE_MODEL.md
docs/phase2_5/runs/20260817-022324-pdf-evidence-v3/V3_REVIEW.md
docs/phase3/PHASE3_IMPLEMENTATION.md
prompts/local_ai/PDF_EVIDENCE_AGENT.md
schemas/pdf_evidence_review.schema.json
schemas/phase3_report.schema.json
```

For Phase 3 persistence details, `docs/architecture/PERSISTENCE_MODEL.md` is normative and supersedes the older persistence sketch in `DESIGN.md` v0.4 where they conflict.

---

# 2. Fixed source boundaries

You MUST preserve:

```text
zotero.sqlite       READ ONLY
Zotero storage PDFs READ ONLY
```

Never run INSERT/UPDATE/DELETE against Zotero. Never annotate, rewrite, move, rename, repair, or optimize user PDFs.

All persistent writes go to Paperazzi-owned SQLite files under ignored runtime paths such as `data/`.

---

# 3. Frozen Phase 2.5 baseline

Treat deterministic PDF v3, including `e06e2bf`, as the frozen parsing baseline for this phase.

You may change PDF code only when necessary to expose **provenance/serialization interfaces** required by Phase 3, for example recording which text channel produced the selected reference section.

Do not change extraction heuristics merely to increase coverage during Phase 3. A parser behavior change requires a concrete regression test and explicit justification.

---

# 4. Phase boundary

Implement only:

```text
SQLAlchemy/Alembic database foundation
split canonical hashes
Zotero scan/diff persistence
current Zotero projections
paper-local creator mentions
PDF document state
extraction run/attempt persistence
evidence-span persistence
reference section/entry/identifier persistence
reserved paper_reference_matches schema
real-library persistence validation
```

Do NOT implement:

```text
author identity resolution
author merge/split
stable author_id assignment
semantic author-affiliation mapping
corresponding-author assignment
reference-to-paper matching
CITES graph edges
online enrichment
FastAPI
frontend
Neo4j/PostgreSQL
OCR integration
```

If you find yourself needing an `authors` table to finish Phase 3, stop and reconsider the design. Phase 3 persists `paper_creator_mentions` instead.

---

# 5. Work in four gated milestones

Follow `docs/phase3/PHASE3_IMPLEMENTATION.md` exactly:

```text
Phase 3A — database foundation/migrations
Phase 3B — split hashes + Zotero diff/persistence
Phase 3C — PDF document/evidence/reference persistence
Phase 3D — real-library validation
```

Do not start the next milestone until the current gate tests pass.

Make each milestone a separate logical commit. If a later validation exposes a general bug, add a synthetic regression test and commit the fix separately before continuing.

---

# 6. Database implementation rules

Use synchronous SQLAlchemy 2.x style.

Paperazzi SQLite connections must enable:

```text
foreign_keys=ON
busy_timeout=5000
WAL for the Paperazzi-owned writable DB
```

Actual schema creation/upgrades must use Alembic. Do not treat `Base.metadata.create_all()` as the production migration mechanism.

Keep database/session/transaction code under:

```text
src/paperazzi/database/
```

Thin scripts may call the services but must not contain core persistence logic.

---

# 7. Identity semantics

Never use Zotero numeric `itemID` as a stable Paperazzi identity.

Zotero identity remains:

```text
(library_id, item_key)
```

Phase 3 creates one `papers` row per Zotero bibliographic item and performs **no DOI/title deduplication**.

A repeated Zotero scan must reuse the existing `paper_id`.

A REMOVED then RESTORED item must also reuse its original `paper_id`.

---

# 8. Hash semantics

Implement and test separate:

```text
bibliographic_hash
organization_hash
attachment_hash
canonical_hash
```

Important examples:

```text
tag changed only          -> organization_hash only
creator changed           -> bibliographic_hash
attachment storage hash   -> attachment_hash
local PDF download state  -> no semantic Zotero hash
Zotero sync/version only  -> no semantic Zotero hash
```

Do not let tag/collection churn trigger future author enrichment semantics.

---

# 9. Scan semantics

Persist explicit:

```text
NEW
MODIFIED
UNCHANGED
REMOVED
RESTORED
```

For MODIFIED also persist dimensions:

```text
BIBLIOGRAPHIC
ORGANIZATION
ATTACHMENT
```

Never physically delete scholarly/evidence history when a Zotero item disappears.

A no-change second real scan is a critical acceptance test: it must not create duplicate papers or item-version rows.

---

# 10. PDF provenance semantics

The final v3 parser may evaluate both:

```text
PYMUPDF_SORTED
PYMUPDF_CONTENT_STREAM
```

Phase 3 must persist which channel produced the selected reference result and which channels were evaluated.

If necessary, add a provenance field to `ReferenceSection`/`PdfEvidence` or add a non-semantic wrapper around the frozen parser. Do not infer the channel later from method names.

Keep distinct:

```text
section_confidence
segmentation_confidence
entry_text_quality
AI review decision/acceptance status
```

A structurally correct numbered chain can still have PARTIAL raw entry text because of layout contamination.

---

# 11. Extraction history semantics

A document can have many extraction runs across time.

Correct uniqueness:

```text
UNIQUE(extraction_run_id, attempt_number)
```

Incorrect:

```text
UNIQUE(document_id, attempt_number)
```

Each extraction run permits attempts 1..3 only.

If Attempt 2 supersedes Attempt 1:

- retain Attempt 1;
- retain its evidence/reference candidates;
- mark statuses appropriately;
- point the extraction cycle to the accepted attempt;
- do not rewrite history.

Runtime AI review output must pass the existing JSON schema before deterministic persistence code accepts it.

---

# 12. Reference semantics

Store:

```text
raw reference section
segmented raw references
DOI/year identifier rows
attempt/source provenance
acceptance state
```

Do not attempt to identify the cited Paperazzi paper in Phase 3.

`paper_reference_matches` may be migrated as an empty reserved table. No accepted match or graph edge is required in this phase.

Raw author-year sections with zero segmented entries are valid persisted evidence.

---

# 13. Testing discipline

Use synthetic data/temporary SQLite databases for behavioral transitions. Never modify the real Zotero database to simulate changes.

Every discovered general bug must follow:

```text
reproduce in test
→ fix implementation
→ rerun gate
```

At each milestone run the entire test suite, not only the new test file.

Use `PRAGMA foreign_key_check` in validation.

Do not commit real databases, snapshots, PDFs, full article text, full bibliographies, or runtime scratch scripts.

---

# 14. Phase 3D real-library validation

After all synthetic tests pass:

1. create a fresh ignored Paperazzi DB;
2. import the complete active Zotero canonical library;
3. immediately repeat the scan with no source changes;
4. verify the second scan is entirely UNCHANGED with no duplicate/version churn;
5. persist a deterministic 200-PDF validation sample into the evidence/reference tables;
6. check the Phase 2.5 anchor cases;
7. test idempotent re-persistence;
8. perform a synthetic failure-injection rollback test.

Do not require full 2161-PDF AI review to pass Phase 3. That is an operational population run after database correctness is established.

---

# 15. Required report and final state

Follow the report fields in `docs/phase3/PHASE3_IMPLEMENTATION.md`. The JSON report must validate against:

```text
schemas/phase3_report.schema.json
```

Commit only compact diagnostics under:

```text
docs/phase3/runs/<timestamp>-phase3/
```

When all acceptance conditions hold, report exactly:

```text
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

Also update repository status documentation only after the tests support that conclusion.

If Phase 3 does not pass, report the failed gate and leave the status unadvanced.