from __future__ import annotations

import importlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*)\s+)?"
    r"(?:references?|bibliography|literature\s+cited|works\s+cited|"
    r"references?\s+and\s+notes|notes\s+and\s+references?)\s*$",
    re.IGNORECASE,
)

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}[a-z]?\b", re.IGNORECASE)

JOURNAL_ABBREV_RE = re.compile(
    r"\b(?:J\.|Jr\.|Phys\.|Chem\.|Acta|Theor\.|Appl\.|Nature|Science|Proc\.|Rev\.|"
    r"Lett\.|Commun\.|Trans\.|Ann\.|Int\.|Ed\.|Biol\.|Med\.|Mater\.|Nano\s|Acc\.)",
    re.IGNORECASE,
)

# Keep deterministic reference ordinals deliberately conservative. The first real-
# library validation showed publication years (1943/1962/1954) being mistaken for
# ordinals. Phase 2.5b additionally showed that noisy marker streams can look locally
# plausible, so v3 selects a strict increasing ordinal chain before segmentation.
NUMBERED_REFERENCE_START_RE = re.compile(
    r"(?m)^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+"
)
PAREN_NUMBERED_REFERENCE_START_RE = re.compile(
    r"(?m)^\s*\((\d{1,3})\)\s*(?=(?:\([a-z]\)\s*)?\S)"
)
BARE_NUMBERED_REFERENCE_START_RE = re.compile(
    r"(?m)^\s*(\d{1,3})\s+(?=[A-ZÀ-ÖØ-Þ])"
)

AFFILIATION_TERMS = (
    "university",
    "universität",
    "universite",
    "université",
    "institute",
    "institut ",
    "instituto",
    "department",
    "departamento",
    "laboratory",
    "laboratoire",
    "school of",
    "college of",
    "faculty of",
    "academy of",
    "national laboratory",
    "national lab",
    "research center",
    "research centre",
    "center for",
    "centre for",
    "center of",
    "centre de",
    "riken",
    "cnrs",
    "max planck",
)

CORRESPONDENCE_TERMS = (
    "corresponding author",
    "correspondence",
    "electronic address",
    "e-mail",
    "email:",
    "email ",
    "to whom correspondence",
)

BOILERPLATE_TERMS = (
    "subscriber access provided by",
    "downloaded via",
    "downloaded from",
    "this article was downloaded by",
    "downloaded by:",
    "articles you may be interested in",
    "publication history",
    "copyright ©",
    "copyright (c)",
)


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    page_index: int
    text: str
    kind: str
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class ReferenceEntry:
    ordinal: int | None
    raw_text: str
    dois: tuple[str, ...] = ()
    years: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceSection:
    heading: str
    start_page: int
    end_page: int
    method: str
    confidence: str
    raw_text: str
    entries: tuple[ReferenceEntry, ...] = ()
    text_channel: str | None = None  # PYMUPDF_SORTED / PYMUPDF_CONTENT_STREAM provenance


@dataclass(frozen=True, slots=True)
class PdfEvidence:
    path: str
    file_size: int | None
    page_count: int
    backend: str
    backend_version: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    text_status: str = "UNKNOWN"
    normal_text_pages: int = 0
    thin_text_pages: int = 0
    empty_text_pages: int = 0
    front_matter_text: str = ""
    front_matter_spans: tuple[EvidenceSpan, ...] = ()
    affiliation_candidates: tuple[EvidenceSpan, ...] = ()
    correspondence_candidates: tuple[EvidenceSpan, ...] = ()
    emails: tuple[str, ...] = ()
    references: ReferenceSection | None = None
    error: str | None = None

    def to_dict(self, *, include_reference_text: bool = True) -> dict[str, Any]:
        result = asdict(self)
        if self.references is not None and not include_reference_text:
            result["references"]["raw_text"] = ""
            for entry in result["references"]["entries"]:
                entry["raw_text"] = ""
        return result


class PdfBackendUnavailable(RuntimeError):
    pass


def _load_pymupdf() -> Any:
    """Import modern ``pymupdf`` first, then the legacy ``fitz`` alias."""
    try:
        return importlib.import_module("pymupdf")
    except ImportError:
        try:
            return importlib.import_module("fitz")
        except ImportError as exc:
            raise PdfBackendUnavailable(
                "PyMuPDF is required for local PDF evidence extraction. "
                "Install the optional 'pdf' dependency or make pymupdf/fitz available."
            ) from exc


def _normalized_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _clean_reference_doi(value: str) -> str:
    value = value.strip()
    while value and value[-1] in ".,;:)]}>\"":
        value = value[:-1]
    return value.lower()


def extract_dois(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for match in DOI_RE.finditer(text):
        doi = _clean_reference_doi(match.group(0))
        if doi and doi not in seen:
            seen.add(doi)
            result.append(doi)
    return tuple(result)


def _reference_marker_number(match: re.Match[str]) -> int | None:
    for group in match.groups():
        if group is not None:
            try:
                number = int(group)
            except ValueError:
                return None
            if number > 999 or 1800 <= number <= 2099:
                return None
            return number
    return None


def _select_strict_ordinal_chain(matches: list[re.Match[str]]) -> list[re.Match[str]]:
    """Return the strongest increasing bibliography-number chain.

    A valid transition increases by 1..10. This tolerates a few missing markers while
    dropping interleaved years, page numbers, OCR artefacts, and unrelated numbered
    material. Dynamic programming is small here because a bibliography normally has
    at most a few hundred markers.
    """
    candidates = [(match, _reference_marker_number(match)) for match in matches]
    candidates = [(match, number) for match, number in candidates if number is not None]
    if len(candidates) < 3:
        return []

    n = len(candidates)
    length = [1] * n
    predecessor = [-1] * n
    gap_cost = [0] * n

    for i in range(n):
        _, current = candidates[i]
        assert current is not None
        for j in range(i):
            _, previous = candidates[j]
            assert previous is not None
            delta = current - previous
            if not 1 <= delta <= 10:
                continue
            candidate_length = length[j] + 1
            candidate_gap_cost = gap_cost[j] + (delta - 1)
            if candidate_length > length[i] or (
                candidate_length == length[i] and candidate_gap_cost < gap_cost[i]
            ):
                length[i] = candidate_length
                predecessor[i] = j
                gap_cost[i] = candidate_gap_cost

    best = max(
        range(n),
        key=lambda i: (
            length[i],
            -gap_cost[i],
            -(candidates[i][1] or 999),
        ),
    )
    if length[best] < 3:
        return []

    indices: list[int] = []
    cursor = best
    while cursor >= 0:
        indices.append(cursor)
        cursor = predecessor[cursor]
    indices.reverse()

    chain = [candidates[index] for index in indices]
    numbers = [number for _, number in chain if number is not None]
    if len(numbers) < 3:
        return []

    # High-confidence automatic splitting requires the chain to be mostly consecutive.
    consecutive = sum(1 for a, b in zip(numbers, numbers[1:]) if b == a + 1)
    if consecutive < max(2, int((len(numbers) - 1) * 0.70)):
        return []

    return [match for match, _ in chain]


def _entries_from_matches(
    normalized: str,
    matches: list[re.Match[str]],
) -> tuple[ReferenceEntry, ...]:
    entries: list[ReferenceEntry] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        raw = " ".join(normalized[start:end].split())
        if not raw:
            continue
        entries.append(
            ReferenceEntry(
                ordinal=_reference_marker_number(match),
                raw_text=raw,
                dois=extract_dois(raw),
                years=tuple(dict.fromkeys(YEAR_RE.findall(raw))),
            )
        )
    return tuple(entries)


def segment_reference_entries(text: str) -> tuple[tuple[ReferenceEntry, ...], str, str]:
    """Best-effort reference segmentation with strict ordinal-chain filtering."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    for pattern, method in (
        (NUMBERED_REFERENCE_START_RE, "numbered-punctuated"),
        (PAREN_NUMBERED_REFERENCE_START_RE, "numbered-parenthesized"),
        (BARE_NUMBERED_REFERENCE_START_RE, "numbered-bare"),
    ):
        chain = _select_strict_ordinal_chain(list(pattern.finditer(normalized)))
        if not chain:
            continue
        entries = _entries_from_matches(normalized, chain)
        if len(entries) >= 3:
            numbers = [entry.ordinal for entry in entries if entry.ordinal is not None]
            # A bracketed/dotted bibliography read under its own heading starts near 1.
            # A consecutive chain that only begins mid-list (e.g. [20, 26, 27...])
            # indicates interleaved two-column text, not a defensible segmentation.
            # Parenthesized footnote numbering legitimately continues from the body,
            # so mid-list starts stay acceptable there.
            if method != "numbered-parenthesized" and numbers and numbers[0] > 5:
                break
            return entries, method, "HIGH"

    # Author-year bibliographies are deliberately not force-split. A raw section with
    # many year anchors remains valuable evidence for local-AI recovery later.
    years = YEAR_RE.findall(normalized)
    if len(years) >= 3:
        return (), "raw-author-year-or-unsegmented", "MEDIUM"
    return (), "raw-unsegmented", "LOW"


_AUTHOR_LIKE_RE = re.compile(
    r"\b[A-Z]\.\s*[A-Z][a-z]"  # dotted initials: A. Author
    r"|\b[A-Z][a-z]+\s+[A-Z]{1,2}\b[,\s]"  # Surname AB,
    r"|\bet\s+al\b",
)


def _head_entries_citation_like(entries: tuple[ReferenceEntry, ...], count: int = 3) -> bool:
    """A bibliography's first entries should themselves be citations.

    Long numbered data/figure sequences can yield strictly increasing chains
    (Phase 2.5c 87JCS8EY regression: energy-statistics lines led the chain).
    Rejecting chains whose head entries lack author-like patterns keeps such
    prose out of paper_reference records.
    """
    for entry in entries[:count]:
        if not _AUTHOR_LIKE_RE.search(entry.raw_text):
            return False
    return True


def _citation_like_ratio(entries: tuple[ReferenceEntry, ...]) -> float:
    """Fraction of sampled entries that look like citations, not numbered prose.

    Data tables and figure sequences can produce long consecutive number chains
    without being bibliographies (Phase 2.5c 87JCS8EY regression: energy statistics
    lines). Require author-initial patterns, journal-style tokens, or "et al".
    """
    if not entries:
        return 0.0
    sample = entries[:50]
    hits = 0
    for entry in sample:
        text = entry.raw_text
        if (
            re.search(r"\b[A-Z]\.\s*[A-Z][a-z]", text)  # dotted initials: A. Author
            or re.search(r"\b[A-Z][a-z]+\s+[A-Z]{1,2}\b[,\s]", text)  # Surname AB,
            or re.search(r"\bet\s+al\b", text, re.IGNORECASE)
            or JOURNAL_ABBREV_RE.search(text)
        ):
            hits += 1
    return hits / len(sample)


def prefer_reference_section(
    primary: ReferenceSection | None, alternate: ReferenceSection | None
) -> ReferenceSection | None:
    """Pick the more trustworthy of two reference-section extractions.

    ``sort=True`` page text interleaves two-column journals and breaks ``[n]``
    line-start markers (Phase 2.5c review: QuTiP-BoFiN, Soriano 2014, IWR2QEJY).
    The caller therefore extracts twice — sorted (reading-order fallback) and raw
    content-stream order — and this rule keeps the better result: chains whose
    entries are not citation-like are rejected; an explicit heading outranks an
    implicit recovery; then more segmented entries win.
    """
    if primary is None:
        return alternate
    if alternate is None:
        return primary

    def qualified(section: ReferenceSection) -> bool:
        if not section.entries:
            return True
        return _head_entries_citation_like(section.entries) and _citation_like_ratio(section.entries) >= 0.5

    def rank(section: ReferenceSection) -> tuple[int, int]:
        return (1 if section.heading else 0, len(section.entries))

    primary_ok = qualified(primary)
    alternate_ok = qualified(alternate)
    if primary_ok != alternate_ok:
        return primary if primary_ok else alternate
    return primary if rank(primary) >= rank(alternate) else alternate


def _find_implicit_numbered_reference_section(pages: list[str]) -> ReferenceSection | None:
    """Conservatively recover a late numbered bibliography without a literal heading.

    Phase 2.5b showed common physics layouts with no extracted References heading and
    multi-line entries whose marker line is the only stable signal. We therefore use
    marker chains rather than single-line citation-density scoring. To avoid inventing
    citation sections from ordinary numbered prose, implicit recovery requires at
    least eight mostly-consecutive entries and a chain beginning near 1.
    """
    if len(pages) < 2:
        return None

    start_page = max(0, int(len(pages) * 0.60))
    tail_pages = pages[start_page:]
    tail_text = "\n\f\n".join(tail_pages)

    best: tuple[int, list[re.Match[str]], str] | None = None
    for pattern, method in (
        (NUMBERED_REFERENCE_START_RE, "implicit-numbered-punctuated"),
        (PAREN_NUMBERED_REFERENCE_START_RE, "implicit-numbered-parenthesized"),
        (BARE_NUMBERED_REFERENCE_START_RE, "implicit-numbered-bare"),
    ):
        chain = _select_strict_ordinal_chain(list(pattern.finditer(tail_text)))
        if len(chain) < 8:
            continue
        numbers = [_reference_marker_number(match) for match in chain]
        numbers = [number for number in numbers if number is not None]
        if not numbers or numbers[0] > 5:
            continue
        score = len(chain)
        if best is None or score > best[0]:
            best = (score, chain, method)

    if best is None:
        return None

    _, chain, method = best
    first_offset = chain[0].start()
    raw_text = tail_text[first_offset:].strip()
    entries = _entries_from_matches(raw_text, list(next(
        pattern.finditer(raw_text)
        for pattern, pattern_method in (
            (NUMBERED_REFERENCE_START_RE, "implicit-numbered-punctuated"),
            (PAREN_NUMBERED_REFERENCE_START_RE, "implicit-numbered-parenthesized"),
            (BARE_NUMBERED_REFERENCE_START_RE, "implicit-numbered-bare"),
        )
        if pattern_method == method
    )))

    # Re-run strict-chain selection in the sliced text; offsets changed after slicing.
    selected_pattern = {
        "implicit-numbered-punctuated": NUMBERED_REFERENCE_START_RE,
        "implicit-numbered-parenthesized": PAREN_NUMBERED_REFERENCE_START_RE,
        "implicit-numbered-bare": BARE_NUMBERED_REFERENCE_START_RE,
    }[method]
    sliced_chain = _select_strict_ordinal_chain(list(selected_pattern.finditer(raw_text)))
    entries = _entries_from_matches(raw_text, sliced_chain)
    if len(entries) < 8:
        return None

    # Approximate the first source page by counting form-feed separators before the
    # chosen start. Exact evidence spans are refined by the AI review when needed.
    local_page_offset = tail_text[:first_offset].count("\f")
    reference_start_page = min(len(pages) - 1, start_page + local_page_offset)
    return ReferenceSection(
        heading="",
        start_page=reference_start_page,
        end_page=len(pages) - 1,
        method=method,
        confidence="HIGH",
        raw_text=raw_text,
        entries=entries,
    )


def find_reference_section(page_texts: Iterable[str]) -> ReferenceSection | None:
    pages = list(page_texts)
    if not pages:
        return None

    minimum_page = max(0, int(len(pages) * 0.30))
    candidates: list[tuple[int, int, str]] = []
    for page_index, page_text in enumerate(pages):
        if page_index < minimum_page:
            continue
        lines = _normalized_lines(page_text)
        for line_index, line in enumerate(lines):
            if REFERENCE_HEADING_RE.fullmatch(line):
                candidates.append((page_index, line_index, line))

    if not candidates:
        return _find_implicit_numbered_reference_section(pages)

    page_index, line_index, heading = candidates[-1]
    first_page_lines = _normalized_lines(pages[page_index])
    first_page_tail = "\n".join(first_page_lines[line_index + 1 :]).strip()
    later_pages = [page.strip() for page in pages[page_index + 1 :] if page.strip()]
    raw_text = "\n\f\n".join([part for part in [first_page_tail, *later_pages] if part]).strip()

    entries, method, confidence = segment_reference_entries(raw_text)
    return ReferenceSection(
        heading=heading,
        start_page=page_index,
        end_page=len(pages) - 1,
        method=method,
        confidence=confidence,
        raw_text=raw_text,
        entries=entries,
    )


def _is_boilerplate(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(term in lowered for term in BOILERPLATE_TERMS)


def _span_from_block(page_index: int, block: tuple[Any, ...], kind: str) -> EvidenceSpan | None:
    if len(block) < 5:
        return None
    text = "\n".join(line.strip() for line in str(block[4]).splitlines() if line.strip()).strip()
    if not text:
        return None
    try:
        bbox = (float(block[0]), float(block[1]), float(block[2]), float(block[3]))
    except (TypeError, ValueError):
        bbox = None
    return EvidenceSpan(page_index=page_index, text=text, kind=kind, bbox=bbox)


def _candidate_spans(
    blocks_by_page: list[list[tuple[Any, ...]]],
    *,
    max_front_pages: int,
) -> tuple[tuple[EvidenceSpan, ...], tuple[EvidenceSpan, ...], tuple[EvidenceSpan, ...], tuple[str, ...]]:
    all_front: list[EvidenceSpan] = []
    affiliations: list[EvidenceSpan] = []
    correspondence: list[EvidenceSpan] = []
    emails: list[str] = []
    seen_email: set[str] = set()

    for page_index, blocks in enumerate(blocks_by_page[:max_front_pages]):
        for block in blocks:
            span = _span_from_block(page_index, block, "front-matter")
            if span is None:
                continue
            all_front.append(span)
            lowered = " ".join(span.text.lower().split())
            if _is_boilerplate(span.text):
                continue

            if any(term in lowered for term in AFFILIATION_TERMS):
                affiliations.append(
                    EvidenceSpan(
                        page_index=span.page_index,
                        text=span.text,
                        kind="affiliation-candidate",
                        bbox=span.bbox,
                    )
                )

            found_emails = [m.group(1).lower().rstrip(".,;:)]}>\"") for m in EMAIL_RE.finditer(span.text)]
            has_correspondence_term = any(term in lowered for term in CORRESPONDENCE_TERMS)
            if found_emails or has_correspondence_term:
                correspondence.append(
                    EvidenceSpan(
                        page_index=span.page_index,
                        text=span.text,
                        kind="correspondence-candidate",
                        bbox=span.bbox,
                    )
                )
            for email in found_emails:
                if email not in seen_email:
                    seen_email.add(email)
                    emails.append(email)

    return tuple(all_front), tuple(affiliations), tuple(correspondence), tuple(emails)


def _text_status(normal: int, thin: int, empty: int, page_count: int) -> str:
    if page_count <= 0:
        return "NO_PAGES"
    if normal == 0 and thin == 0:
        return "NO_TEXT_LAYER"
    if normal == 0:
        return "THIN_TEXT_LAYER"
    coverage = normal / page_count
    if coverage >= 0.80:
        return "NATIVE_TEXT_GOOD"
    if coverage >= 0.40:
        return "NATIVE_TEXT_PARTIAL"
    return "NATIVE_TEXT_SPARSE"


def extract_pdf_evidence(path: str | Path, *, max_front_pages: int = 2) -> PdfEvidence:
    """Read a local PDF and return deterministic evidence without changing the file."""
    pdf_path = Path(path).expanduser().resolve()
    try:
        file_size = pdf_path.stat().st_size
    except OSError as exc:
        return PdfEvidence(
            path=str(pdf_path),
            file_size=None,
            page_count=0,
            backend="PyMuPDF",
            backend_version=None,
            text_status="FILE_UNAVAILABLE",
            error=str(exc),
        )

    try:
        pymupdf = _load_pymupdf()
    except PdfBackendUnavailable as exc:
        return PdfEvidence(
            path=str(pdf_path),
            file_size=file_size,
            page_count=0,
            backend="PyMuPDF",
            backend_version=None,
            text_status="BACKEND_UNAVAILABLE",
            error=str(exc),
        )

    backend_version = getattr(pymupdf, "__version__", None)
    page_texts: list[str] = []
    page_texts_plain: list[str] = []
    blocks_by_page: list[list[tuple[Any, ...]]] = []
    metadata: dict[str, Any] = {}

    try:
        with pymupdf.open(str(pdf_path)) as doc:
            if getattr(doc, "needs_pass", False):
                return PdfEvidence(
                    path=str(pdf_path),
                    file_size=file_size,
                    page_count=int(getattr(doc, "page_count", 0)),
                    backend="PyMuPDF",
                    backend_version=backend_version,
                    metadata=dict(getattr(doc, "metadata", {}) or {}),
                    text_status="PASSWORD_REQUIRED",
                    error="PDF requires a password",
                )

            metadata = dict(doc.metadata or {})
            for page in doc:
                sorted_text = page.get_text("text", sort=True) or ""
                page_texts.append(sorted_text)
                page_texts_plain.append(page.get_text("text") or "")
                raw_blocks = page.get_text("blocks", sort=True) or []
                text_blocks = [tuple(block) for block in raw_blocks if len(block) < 7 or block[6] == 0]
                blocks_by_page.append(text_blocks)
    except Exception as exc:
        return PdfEvidence(
            path=str(pdf_path),
            file_size=file_size,
            page_count=0,
            backend="PyMuPDF",
            backend_version=backend_version,
            metadata=metadata,
            text_status="OPEN_OR_PARSE_ERROR",
            error=f"{type(exc).__name__}: {exc}",
        )

    normal = sum(1 for text in page_texts if len(text.strip()) >= 200)
    thin = sum(1 for text in page_texts if 1 <= len(text.strip()) < 200)
    empty = sum(1 for text in page_texts if not text.strip())

    front_spans, affiliations, correspondence, emails = _candidate_spans(
        blocks_by_page,
        max_front_pages=max_front_pages,
    )
    front_text = "\n\f\n".join(page_texts[:max_front_pages]).strip()
    primary = find_reference_section(page_texts)
    alternate = find_reference_section(page_texts_plain)
    references = prefer_reference_section(primary, alternate)
    if references is not None:
        # Provenance only: record which text channel produced the accepted result.
        # Parser heuristics are unchanged (frozen v3 baseline).
        references = ReferenceSection(
            heading=references.heading,
            start_page=references.start_page,
            end_page=references.end_page,
            method=references.method,
            confidence=references.confidence,
            raw_text=references.raw_text,
            entries=references.entries,
            text_channel=(
                "PYMUPDF_SORTED"
                if references is primary
                else "PYMUPDF_CONTENT_STREAM"
            ),
        )

    return PdfEvidence(
        path=str(pdf_path),
        file_size=file_size,
        page_count=len(page_texts),
        backend="PyMuPDF",
        backend_version=backend_version,
        metadata=metadata,
        text_status=_text_status(normal, thin, empty, len(page_texts)),
        normal_text_pages=normal,
        thin_text_pages=thin,
        empty_text_pages=empty,
        front_matter_text=front_text,
        front_matter_spans=front_spans,
        affiliation_candidates=affiliations,
        correspondence_candidates=correspondence,
        emails=emails,
        references=references,
        error=None,
    )


__all__ = [
    "EvidenceSpan",
    "PdfBackendUnavailable",
    "PdfEvidence",
    "ReferenceEntry",
    "ReferenceSection",
    "extract_dois",
    "extract_pdf_evidence",
    "find_reference_section",
    "segment_reference_entries",
]
