# Phase 2.5c — Deterministic v3 review (local AI)

Run: `20260817-022324-pdf-evidence-v3` (200-document stratified sample, deterministic
selection identical to the Phase 2.5 pool).

## Unit-test gate

`python -m unittest discover -s tests -v` → **24/24 OK**, covering all required v3
regressions (years-not-ordinals, strict chains, `(n)`/`(n)(a)`, multi-line implicit
recovery, short-list rejection, noise rejection) plus the two regressions added
during this review (see fixes below).

## v1 → v3 comparison

```text
unit_tests_passed                        10 → 24
selected_documents                      200 = 200
parse_errors                              0 = 0

v1_reference_sections                    45
v3_reference_sections                   153
v3_explicit_reference_headings          106
v3_implicit_reference_sections           47
v1_segmented_reference_documents         30
v3_segmented_reference_documents        122
v1_segmented_reference_entries         ~785
v3_segmented_reference_entries        7363
v3 DOIs inside segmented references      61

new_implicit_sections_reviewed           47 (all genuine bibliographies)
new_implicit_false_positives              0
parenthesized_cases_reviewed             48 (35 implicit + 13 explicit)
parenthesized_false_splits                0
ordinal_chain_false_positives             0 in final run (1 pre-fix, fixed)
```

## Issues found during review and fixed during the run

The first v3 run (pre-fix, `pdf-evidence-output/20260817-021152-pdf-evidence-v3`)
recovered 80 sections but AI review found one shared root cause:

**`get_text("text", sort=True)` interleaves two-column journals**, breaking
`[n]`-at-line-start markers. Consequences observed: QuTiP-BoFiN unrecovered
(80→43 markers, chain 78→21); Soriano recovered only 12/47 entries with
column-interleaved text; `IWR2QEJY` produced a `HIGH` chain starting at 20
(`[20, 26, 27…]`) — a partial reproduction of the old implausible-HIGH defect.

Fixes committed as `e06e2bf` (code + tests, separate from this report):

1. **Dual text-channel extraction** — references are extracted from both
   `sort=True` and content-stream page text; `prefer_reference_section` keeps the
   better result (citation-like gates, then explicit heading, then entry count).
2. **Mid-list chain rejection** — a bracketed/dotted chain under an explicit
   heading that begins above 5 falls back to raw instead of a false `HIGH`
   (parenthesized footnote numbering is exempt: it legitimately continues from
   the body).
3. **Citation-like qualification** — chains whose head entries or majority lack
   author-like/journal patterns are rejected (regression: `87JCS8EY` energy-data
   lines had produced a 199-entry false chain in an intermediate fix).
4. Regression tests for all three rules.

## Anchor checks (final run)

- **QuTiP-BoFiN** — `implicit-numbered-punctuated/HIGH n=78`, ordinals 1..N
  consecutive, first entry `[1] H.-P. Breuer and F. Petruccione…`. Now recovered
  deterministically at Attempt 1; the Phase 2.5b Round-3 block reconstruction is
  no longer needed. ✔
- **Rota 1964** — remains `raw-author-year-or-unsegmented/MEDIUM n=0`;
  1943/1962/1954 never appear as ordinals. ✔
- **Soriano & Palacios 2014** — `implicit n=47` (was 12 with interleaved text);
  front-matter affiliation and e-mail evidence intact. ✔
- **Implausible-HIGH cases** — `IWR2QEJY`: explicit `References`, `n=47`, chain
  from 1 (old `[20,2,3…]` gone). `87JCS8EY`: `n=64`, chain from 1; first entries
  still interleave body text (Nature two-line layout) — recorded as a known
  long-tail limitation, not a false chain. ✔
- **Footnote style** — `J99X9MWN` (JACS communication) now recovered as
  `implicit-numbered-parenthesized n=9` starting at 4; verified correct
  (footnote numbering continues from the body; position at 33% is the footnote
  zone of a 3-page communication). This was an Attempt-3 case in Phase 2.5b. ✔

## AI review of the final 200-doc JSON

- All 47 implicit sections: genuine bibliographies, latter-part positions,
  chain starts ≤ 5, no year-like ordinals, head/tail entries citation-like.
- One flagged-by-heuristic case (`J99X9MWN`, position 0.33 + mid-list start)
  manually verified as correct footnote-style recovery.
- 61 newly explicit headings (v1 missed them due to `sort=True` mangling) spot
  checked — consistent with the Phase 2.5b AI-supervised results where they
  overlap (`AVQHTZD2` 10, `CGBPQC3L` 29, `QE7W7XUJ` 22 entries).

## Retry-reduction estimate (Phase 2.5b 40-document set)

```text
2.5b Attempt-2 executions                 30 → ~6 still needed (24 now deterministic)
2.5b Attempt-3 executions                   5 → 0 still needed (all 5 deterministic:
                                               QuTiP-BoFiN, J99X9MWN, IWR2QEJY,
                                               87JCS8EY, 8JCK959A)
```

## Recommendation

```text
PHASE_2_5_STATUS = PASS
DETERMINISTIC_PDF_BASELINE = FROZEN_V3 (with fix e06e2bf)
NEXT_PHASE = PHASE_3_PERSISTENCE
```

Rationale: all acceptance conditions hold — tests pass; no year-as-ordinal or
implausible-HIGH regressions; implicit recovery shows no material false-positive
pattern in the reviewed sample; parenthesized handling creates no false subreference
splits; failures remain non-fatal (0 parse errors); and the deterministic layer now
absorbs the large majority of previously manual retries. Remaining long-tail
(Nature-style separated numbering, complex author-year bibliographies, OCR-only
scans, broken PDFs) stays under AI supervision as designed.
