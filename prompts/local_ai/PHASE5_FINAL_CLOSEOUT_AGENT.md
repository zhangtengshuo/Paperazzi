# Paperazzi Phase 5 — Final Closeout Agent v4

You are performing the **final Phase 5 closeout validation** on the user's real local Paperazzi database and browser environment.

The authoritative specification is:

```text
docs/phase5/PHASE5_FINAL_VALIDATION.md
```

Read that file completely before executing anything. It overrides older Phase 5 validation prompts where they differ.

## Hard rules

1. Use only the dedicated micromamba environment named exactly `Paperazzi` for authoritative Paperazzi work.
2. Do not install/upgrade/downgrade/uninstall anything in Anaconda base, system Python, or unrelated environments.
3. Do not modify Zotero `zotero.sqlite`, Zotero `storage/`, or PDFs.
4. Do not alter Phase 4 identity thresholds or hide unresolved authors to make tests pass.
5. Do not claim `PHASE_5_STATUS = PASS` when any mandatory test is omitted.
6. A real browser semantic smoke is mandatory. ASGI/Uvicorn HTTP 200 checks do not replace it.
7. If a mandatory step cannot be run, report `INCOMPLETE`; do not fabricate evidence.
8. Do not suppress project-originated warnings. Record them.
9. Do not add FTS5/caching or other broad optimizations during validation unless a reproducible defect is first established and the user explicitly asks for that fix.

## Specific regression under test

The old real-db identity-review endpoint baseline was:

```text
ASGI /api/reviews/identity?limit=5 = 451.042 ms
Uvicorn /api/reviews/identity?limit=5 = 447.136 ms
```

The new implementation replaces the old all-rows + N+1 lookup path with one bounded SQL query. Verify:

```text
test_identity_review_queue_is_ranked_with_one_select = PASS
```

Then remeasure the real Uvicorn endpoint exactly as required by `PHASE5_FINAL_VALIDATION.md`. Report raw timings; do not report only a qualitative statement.

## Required output

Create:

```text
docs/phase5/runs/YYYYMMDD-HHMMSS-final-closeout-v4/PHASE5_FINAL_VALIDATION_REPORT.md
```

The report must contain every mandatory field and evidence section specified in `docs/phase5/PHASE5_FINAL_VALIDATION.md`.

Before committing, run the machine gate:

```bash
micromamba run -n Paperazzi python scripts/check_phase5_closeout_report.py <REPORT_PATH>
```

If the checker does not print `PHASE 5 CLOSEOUT REPORT: PASS`, do **not** commit a report claiming Phase 5 PASS. Fix the missing evidence or truthfully report FAIL/INCOMPLETE.

## Information especially important to return to remote review

Return concrete measured values for:

```text
current commit SHA
full regression test count/runtime
all project-originated warnings
full corpus paper/author/mention counts
unresolved-author visibility count
projection mismatch count
FK check rows
PDF available/reachable/stale counts
ASGI route timings
Uvicorn route timings
identity-review 5+ raw post-warmup timings and median
identity-review performance class
each extended real search case
real PDF 200 paper ID
real unavailable-PDF paper ID and controlled status
browser-checked unresolved-author paper ID
browser-checked corresponding-author paper ID
browser-checked author profile ID
high-publication author ID/count/timing
high-degree author ID/count/timing
identity precision audit result or NOT_RUN_OPTIONAL
```

If a defect is found, preserve the failing IDs/timings/traceback first. Only then make the smallest responsible fix, add a regression test, rerun the full required sequence, and clearly separate pre-fix from post-fix evidence in the report.
