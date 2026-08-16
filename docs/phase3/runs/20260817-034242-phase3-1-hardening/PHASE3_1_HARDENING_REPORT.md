# Phase 3.1 Persistence Hardening Validation

Generated: 2026-08-17 03:42:42 Asia/Shanghai
Validation script: `scripts/validate_phase3.py`

## Result

```text
PHASE_3_1_STATUS = PASS
PHASE_3_STATUS = PASS
PAPERAZZI_DB_SCHEMA = PHASE3_V1
NEXT_PHASE = PHASE_4_IDENTITY_AND_RESOLUTION
```

All post-Phase-3 persistence-hardening invariants covered by the Phase 3.1 specification passed. Phase 4 is unblocked.

## Gates

| Gate | Result |
|---|---|
| Unit/regression suite | 46 passed, 0 failed |
| Migration head | `0003_extraction_reviews (head)` |
| `PRAGMA foreign_key_check` | 0 rows |
| Duplicate Zotero identities | 0 |
| Rollback injection | `FAILED` scan, `FAILED` scan row, 0 paper rows |

## Full Zotero scans

| Metric | First scan | Second scan |
|---|---:|---:|
| `NEW` | 2513 | 0 |
| `MODIFIED` | 0 | 0 |
| `UNCHANGED` | 0 | 2513 |
| `REMOVED` | 0 | 0 |
| `RESTORED` | 0 | 0 |

Persisted counts:

- Zotero items/papers: 2513 / 2513
- Creator mentions: 12381
- All Zotero attachments: 2567
- PDF documents: 2374; expected PDF attachments: 2374
- `PDF_AVAILABLE`: 2161; expected local PDFs: 2161
- Non-PDF `paper_documents`: 0
- Item-version rows: 2513

## Deterministic 200-PDF sample

- Candidate Attempt 1 rows: 200
- Candidate evidence spans: 393; accepted evidence spans: 0
- Candidate reference sections: 153; accepted sections: 0
- Candidate reference entries: 7363; accepted references: 0
- Review rows during deterministic validation: 0
- Runs still `STARTED`/review-pending: 200
- Documents with current accepted extraction run: 0
- Duplicate pending extraction triggers: 0

All deterministic outputs remained `REVIEW_PENDING`/`CANDIDATE`; no acceptance occurred without an AI/manual review row.

## Anchor states

| Anchor | Result |
|---|---|
| QuTiP-BoFiN (`I97Q72KK`) | 78 entries; `PYMUPDF_CONTENT_STREAM`; section HIGH; segmentation HIGH; entry text `UNREVIEWED` |
| Rota 1964 (`MD8N7CDD`) | raw section; 0 entries; `PYMUPDF_SORTED`; section HIGH; segmentation NULL; entry text `UNREVIEWED` |
| Soriano 2014 (`QRV8DDP9`) | 47 entries; `PYMUPDF_CONTENT_STREAM`; section HIGH; segmentation HIGH; entry text `UNREVIEWED` |
| JACS footnote (`J99X9MWN`) | 9 entries; `PYMUPDF_CONTENT_STREAM`; section HIGH; segmentation HIGH; entry text `UNREVIEWED` |
| Nature-style (`87JCS8EY`) | 64 entries; `PYMUPDF_SORTED`; section HIGH; segmentation HIGH; entry text `UNREVIEWED` |

## Notes

MuPDF emitted color-space parsing warnings for a small number of PDFs during extraction. The validator completed successfully and all required assertions passed.

The generated raw JSON validation output is in the ignored runtime path `data/phase3-validation/phase3_hardening_report.json`.
