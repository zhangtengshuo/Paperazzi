# WoS Import Observation and Merge Policy

## Purpose

Web of Science Plain Text exports are treated as **observations of a stable WoS record (`UT`)**, not as immutable one-time source rows.

This policy exists because repeated WoS exports of the same Full Record are not guaranteed to contain identical payloads. In particular, WoS may report a non-zero cited-reference count (`NR`) while omitting the actual cited-reference list (`CR`) in a later export.

Therefore:

> Re-importing an existing `UT` is expected and must be non-destructive.

The independent WoS corpus must accumulate the best available information across observations instead of rejecting duplicates or replacing richer data with poorer exports.

---

## 1. Record identity

`UT` remains the primary identity of a WoS Full Record.

Repeated imports with the same `UT`:

- do **not** create a second canonical record;
- do **not** get rejected merely because the `UT` already exists;
- create a new import observation;
- compare and merge useful fields into the canonical record.

The raw text of each observation is retained in `wos_record_observations` together with its import batch.

---

## 2. Cited-reference completeness

Clarivate Plain Text uses:

```text
NR = Cited Reference Count
CR = Cited References
```

Paperazzi classifies each imported observation separately.

### `COMPLETE`

`CR` is present and the parsed CR count is at least the reported `NR` count.

### `COMPLETE_ZERO`

`NR=0` and no CR rows are present.

This is a genuine zero-reference record, not an export failure.

### `MISSING_FROM_EXPORT`

`NR>0` but no `CR` payload is present.

This is the important WoS export-gap state. It must be recorded and must **not** erase cited references obtained from an earlier observation.

### `PARTIAL`

`CR` is present, but fewer CR rows were parsed than the reported `NR` count.

### `PRESENT_UNVERIFIED`

CR rows are present but `NR` is absent, so the list is useful but completeness cannot be mechanically verified.

### `UNKNOWN`

Neither an informative `NR` nor a usable CR payload is available.

---

## 3. Canonical cited-reference merge

`wos_cited_references` represents the best accumulated local CR set for a `UT`.

Rules:

1. An incoming observation with no CR rows never deletes existing canonical references.
2. Incoming CR rows are merged with existing CR rows.
3. DOI is the preferred deduplication key when available.
4. References without DOI are deduplicated by normalized raw-reference text.
5. Citation targets are re-resolved after each import.
6. A cited DOI is linked to a local target `UT` only when that DOI uniquely identifies one local WoS record.

A later complete export can therefore repair an earlier `MISSING_FROM_EXPORT` record without creating a duplicate Full Record.

---

## 4. Other metadata merge

Repeated exports are also allowed to complement non-reference metadata.

Canonical scalar fields use non-destructive update semantics:

- a new non-empty value may update the canonical value;
- an absent value must not overwrite an existing non-empty value.

Repeated structured collections such as authors, identifiers, addresses, organizations, correspondence groups, e-mails, keywords, classifications and funding data are merged rather than globally cleared before every re-import.

The raw observation remains available when later conflict-resolution logic needs to distinguish historical variants from the current canonical projection.

---

## 5. Observation provenance

Each imported Full Record observation records at least:

```text
UT
batch_id
observed_at
WoS data/export date when available
raw Full Record text
whether a CR tag was present
parsed CR count
reported NR count
CR export status
```

This makes an export failure itself queryable evidence rather than an invisible absence.

Useful commands:

```bash
paperazzi-wos stats
paperazzi-wos cr-gaps --limit 200
paperazzi-wos observations WOS:XXXXXXXXXXXXXXX
```

`cr-gaps` is intended to guide later manual WoS re-export work. It does not imply that the affected paper is missing from WoS; it means the local corpus does not yet have a mechanically complete cited-reference payload for that record.

---

## 6. Operational consequence

The normal manual workflow is now:

```text
broad WoS search/export
        ↓
import all records, including repeated UTs
        ↓
record each export observation
        ↓
non-destructive canonical merge
        ↓
inspect cr-gaps
        ↓
later broad/targeted WoS export may complement the same UTs
        ↓
merge again
```

There is no requirement to obtain complete CR data for every WoS record before Paperazzi can use the corpus. CR completeness is a tracked quality dimension, not a global ingestion gate.
