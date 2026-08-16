# Phase 2.5b — AI-supervised adaptive PDF extraction validation report

- Generated: 2026-08-17 (local AI run per `docs/phase2_5/AI_ADAPTIVE_REVIEW_VALIDATION.md`)
- Agent spec: `prompts/local_ai/PDF_EVIDENCE_AGENT.md` @ `bb7cb47`
- Output contract: `schemas/pdf_evidence_review.schema.json` (validated)
- Corpus: 40 documents selected from the Phase 2.5 200-doc run
  (A: 10 deterministic-good, B: 10 native-good/references-null, C: 10 MEDIUM/raw or
  implausible-HIGH, D: 10 noise/historical/broken), years 1950–2023.
- Unit tests before the batch: **18/18 OK**, including the year-as-ordinal regression.

## Aggregate result

```text
selected_documents                          40
attempt1  PASS / ACCEPT_PARTIAL / RETRY      6 / 3 / 30
attempt1  UNRESOLVED / NEEDS_OCR             1 / 0
attempt2  executed / resolved               30 / 24
attempt3  executed / resolved                5 / 3
final     PASS / ACCEPT_PARTIAL             14 / 24
final     UNRESOLVED / NEEDS_OCR             1 / 1
max attempts per document                    3 (never exceeded)

reference sections      before AI review 20  → after 37
segmented ref documents before           11  → after 17
reference entries        before          398  → after 552
```

## Retry strategies used

```text
strategy                                          count  success
TAIL_REFERENCE_RECOVERY                              18       16
ALTERNATIVE_REFERENCE_SEGMENTATION (author-year)     11        8
ZOTERO_FT_CACHE_FALLBACK                              1        0
A3: BLOCK_COLUMN_RECONSTRUCTION + numbered-chain      1        1
A3: strict-lis-chain                                  3        2
A3: wider-tail-footnote-raw                           1        1
```

## AI-rejected false positives

- Reference outputs: 3 — two deterministic `HIGH` segmentations with implausible
  ordinals (`IWR2QEJY` [20,2,3,…], `87JCS8EY` [3,6,1,2,9,3,…]) and one A2 raw tail
  that was acknowledgments text, not references (`JL9YDTZ3`).
- Affiliation candidates: 10 documents had ≥1 candidate rejected (download banners
  "Downloaded by [Marquette University]" / "This article was downloaded by",
  AIP publisher blocks, JCP page headers, body prose, OCR debris).
- Correspondence candidates: 2 rejected (a prose sentence; an RSC
  "Email alerting service" block on a 1950 scan).

## Manual anchor checks

1. **Rota 1964 (`MD8N7CDD`)** — publication years 1943/1962/1954 are no longer
   accepted as ordinals: Attempt 1 now returns `raw-author-year/MEDIUM, n=0` with the
   raw section preserved; no force-split. ✔
2. **QuTiP-BoFiN (`I97Q72KK`)** — Attempt 1 `references=null`; Attempt 2 density-window
   failed (root cause: each PRR entry spans 2–3 lines and the `[n] Author…` first line
   scores 0); Attempt 3 block inspection + numbered chain recovered **78 entries,
   77/77 consecutive, 1..78** on pages 15–17. ✔
3. **Soriano & Palacios 2014 (`QRV8DDP9`)** — Attempt 2 recovered 44 numbered entries;
   affiliation block and `*maria.soriano@uam.es` / `†juanjose.palacios@uam.es`
   correspondence evidence genuine. ✔
4. **Publisher noise (`PDKPCZ27`, `CGBPQC3L`)** — "Downloaded by …" banners rejected
   as affiliation evidence; genuine affiliations (Stuttgart) retained. ✔

## Findings for the next implementation step

1. **Multi-line reference entries break single-line density windows.** The
   citation-density criterion must score entry-start lines (`[n]`, `n.`, `n)`) as
   citation-like even when the author/journal tokens continue on later lines.
   Fixing this one rule would have resolved QuTiP at Attempt 2.
2. **Strict ordinal-chain (LIS) segmentation** cleanly repaired one implausible-HIGH
   document (47/47 consecutive) and is a cheap post-filter for numbered outputs.
3. **Footnote-style bibliographies** (JACS communications, `(8) (a) Author…`) need a
   `(`-opener pattern in any future deterministic parser.
4. **Nature-style two-line entries** keep numbers visually separated from text;
   line-level regexes cannot segment them — raw preservation is the correct v1
   behavior (no false citation edges).
5. **Attempt-2 author-year estimators under-count** (book/review bibliographies);
   they are acceptable only as conservative raw annotations, never as counts.
6. **Zotero ft-cache is not a references fallback** for old scans — the 1950 scan's
   cache holds 1403 chars of front-matter only. OCR remains the only route there.
7. Zero-page/corrupt PDFs terminate cleanly as `UNRESOLVED` without batch impact.

## Provenance

- All PDFs and `zotero.sqlite` opened read-only; no committed parser source edited
  during the batch; document-specific analysis scripts were temporary
  (`/tmp/p25b_*.py`), outside the repository.
- Per-document attempt histories, decisions, strategies, and quality notes:
  `ai_review_report.json` (schema-validated).
