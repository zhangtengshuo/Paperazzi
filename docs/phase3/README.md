# Phase 3 — Paperazzi persistence

Phase 3 starts after:

```text
PHASE_2_5_STATUS = PASS
DETERMINISTIC_PDF_BASELINE = FROZEN_V3
```

Its purpose is to build the first durable, incrementally updateable Paperazzi database.

## Read in this order

```text
1. docs/architecture/PERSISTENCE_MODEL.md
2. docs/phase3/PHASE3_IMPLEMENTATION.md
3. prompts/local_ai/PHASE3_IMPLEMENTATION_AGENT.md
4. schemas/phase3_report.schema.json
```

Supporting source-boundary documents remain mandatory:

```text
docs/architecture/ZOTERO_DATA_BOUNDARY.md
docs/architecture/LOCAL_PDF_EVIDENCE.md
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
prompts/local_ai/PDF_EVIDENCE_AGENT.md
schemas/pdf_evidence_review.schema.json
```

## Four milestones

```text
3A  SQLAlchemy/Alembic foundation and migrations
3B  split hashes + Zotero scan/diff persistence
3C  PDF document/extraction/evidence/reference persistence
3D  real-library validation and idempotency/rollback checks
```

Each milestone is gated by tests and should be committed separately.

## Critical Phase 3 boundaries

Phase 3 persists **paper-local creator mentions**, not resolved authors.

It also persists raw references but does **not** match them to cited papers.

Therefore Phase 3 must not implement:

```text
author identity
citation matching
CITES graph
online enrichment
API/frontend
```

## Expected completion state

```text
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

Runtime databases, Zotero snapshots, PDFs, full extracted text and local-AI scratch files must remain outside Git.