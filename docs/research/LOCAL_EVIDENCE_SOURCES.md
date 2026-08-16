# Local evidence reconnaissance — affiliations, references, PDF parsing

Date: 2026-08-17. Executed against the real local library described in
[`docs/phase2/PHASE2_ANALYSIS.md`](../phase2/PHASE2_ANALYSIS.md).

**Status: informational reconnaissance for the enrichment design. It does not modify
the [Zotero data boundary](../architecture/ZOTERO_DATA_BOUNDARY.md).** That boundary
explicitly keeps PDF parsing out of the Zotero ingestion layer; everything below is
positioned as *candidate local evidence for the later enrichment domain*, with
provenance kept separate from Zotero-derived facts.

## Question

After Phase 2 mapped the corpus, three reconnaissance questions were tested locally:

1. Where does Zotero keep its PDF full-text parsing results, and do they contain
   author affiliation information?
2. Can each paper's reference list be obtained without opening the PDF as a document?
3. Does the local Python environment have stable PDF parsing capability for these
   extractions?

## Finding A — Zotero full-text infrastructure

| Location | Content |
|----------|---------|
| `zotero.sqlite` table `fulltextItems` | 2413 rows: page/char counts, version, sync state — no text |
| `zotero.sqlite` tables `fulltextWords` / `fulltextItemWords` | inverted word index for search — not continuous text |
| `storage/<attachment-key>/.zotero-ft-cache` | extracted plain text; 1151 files present |
| `storage/<attachment-key>/.zotero-ft-unprocessed` | same text wrapped in JSON (`{"indexedPages",…,"text"}`); 23 files pending |

Structured item metadata contains **no author affiliations and no reference lists**:

- `fieldsCombined` has no affiliation-like field; `institution` (manuscript/report)
  and `university` (thesis) are publication fields, and `references` exists only on
  the `patent` type with 0 uses in this library;
- `itemRelations` (883 rows) only carries `dc:relation` / `dc:replaces` — manual
  "related items", not citation edges;
- `itemNotes` (550 rows) are user notes; a number of them store Web-of-Science
  "Times Cited" counts captured manually — a bonus local signal, provenance "user note".

## Finding B — affiliations are recoverable from page-1 text

Verified on real papers (via both the Zotero caches and direct PDF parsing):

- Soriano & Palacios 2014, PRB 90, 075128 — full address block under the author line
  ("Departamento de Física de la Materia Condensada, IFIMAC… Universidad Autónoma de
  Madrid, 28049 Madrid, Spain");
- QuTiP-BoFiN 2023, PRResearch 5, 013181 — numbered affiliation list
  (1 RIKEN, 2 Chalmers/MC2, 3 Aberystwyth, 4 Erlangen-Nürnberg, …) with superscript
  author markers;
- Verbeek & Van Lenthe 1991, Theor. Chim. Acta — "University of Utrecht, Padualaan 14,
  3584 CH Utrecht";
- Picconi et al., PCCP (PySurf, ESI PDF) — Düsseldorf + Heidelberg institutes;
- JCP 153, 020901 (2020) — UC Berkeley Pitzer Center + Boston University.

Two dominant layouts must be handled: numbered-superscript lists and address blocks.
Extraction noise exists (e.g. ACS "Subscriber access provided by …" lines).

## Finding C — reference lists are recoverable without opening PDFs

- Soriano & Palacios 2014: ~47 numbered entries (journal-abbreviated style);
- QuTiP-BoFiN 2023: ~66 numbered entries;
- Verbeek & Van Lenthe 1991: "Bibliography", 10 entries;
- Rota 1964: author–year style (unnumbered but complete).

This enables **in-library citation edges**: parse each paper's reference entries and
match them (title/DOI/journal+volume+page) against the canonical corpus — a local
seed for the planned `graph/` module with no network access. Full citation graphs
still require external sources (Crossref/OpenCitations).

## Finding D — local PDF parsing capability

Environment: WSL2, anaconda3 Python 3.13.9. Available: **PyMuPDF (`fitz`)** — primary;
`pypdf`, `PyPDF2` — fallbacks. Not installed in this env: pdfplumber, pdfminer,
mineru (a local MinerU workspace exists separately), poppler-utils, tesseract.

Test on five real PDFs (read-only, from `storage/`):

| Paper | Pages | Time | Affiliations | References |
|-------|-------|------|--------------|------------|
| Soriano & Palacios 2014 | 11 | 110 ms | yes | ~47 entries |
| QuTiP-BoFiN 2023 | 18 | 92 ms | yes (+ embedded PDF title/author metadata) | ~66 entries |
| Verbeek & Van Lenthe 1991 | 10 | 48 ms | yes | 10 entries |
| Rota 1964 | 29 | 92 ms | no (poor scan layer) | yes (author–year) |
| King et al. 1967 | 7 | 73 ms | no | no — needs OCR |

Coverage sampling: 150 of 2216 `.pdf` files under `storage/` → 146 with a normal
page-1 text layer (≈97%), 3 thin, 1 absent, 0 failed to open. Estimated 50–70
scanned PDFs (mostly 1960s–70s) require OCR fallback.

Advantages over relying on Zotero's caches: independent of Zotero indexing state
(ft-cache exists for only about half the PDFs), millisecond speed, and access to
PDF-embedded metadata. Both routes read identical publisher text layers.

## Implications for Paperazzi

1. **Ingestion stays unchanged** per the data boundary: `zotero_sqlite` reads
   metadata only; nothing here weakens that rule.
2. **Enrichment gains local evidence sources** with explicit provenance values such
   as `local-pdf` and `zotero-fulltext-cache`: affiliations (for `identity/`),
   in-library citation edges (for `graph/`), citation counts from user notes.
3. Corresponding-author status could be mined from PDF footnotes/acknowledgements
   (marked authors) — but this stays a *local-evidence* claim, weaker than the online
   sources the boundary document prescribes, and must remain distinguishable.
4. Missing-text scans (~3%) need an OCR path (MinerU local service or tesseract;
   neither is currently wired into this repo).

## Provenance

- Zotero database opened `mode=ro` + `immutable=1`; no writes to any Zotero file.
- PDF extraction script (read-only): `/tmp/test_pdf_extract.py` (ephemeral, not committed).
- Library state during reconnaissance: 5714 items, 2216 stored PDFs, 2448 storage
  directories.
