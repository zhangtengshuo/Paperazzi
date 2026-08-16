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
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}[a-z]?\b", re.IGNORECASE)

# Reference ordinals above 999 are not useful for the scholarly corpus we target and
# are much more likely to be publication years/OCR artefacts.  The first real-library
# validation showed author-year bibliographies being misread as ordinals such as
# 1943/1962/1954, so keep the deterministic baseline deliberately conservative.
NUMBERED_REFERENCE_START_RE = re.compile(
    r"(?m)^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+"
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
    while value and value[-1] in ".,;:)\]}>":
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
            # Defensive even if a future regex becomes wider again.
            if number > 999 or 1800 <= number <= 2099:
                return None
            return number
    return None


def _markers_are_plausible(markers: list[tuple[int, int]]) -> bool:
    """Require enough locally near-sequential markers before trusting splitting."""
    if len(markers) < 3:
        return False
    numbers = [number for _, number in markers]
    if any(number < 1 or number > 999 for number in numbers):
        return False

    deltas = [b - a for a, b in zip(numbers, numbers[1:])]
    if not deltas:
        return False

    # Extraction may skip a few markers, especially across columns/pages, but real
    # bibliography numbering should not look like a sequence of publication years or
    # make huge arbitrary jumps.  Require at least ~70% small forward moves.
    plausible_forward = sum(1 for delta in deltas if 1 <= delta <= 50)
    required = max(2, (len(deltas) * 7 + 9) // 10)
    return plausible_forward >= required


def segment_reference_entries(text: str) -> tuple[tuple[ReferenceEntry, ...], str, str]:
    """Best-effort reference segmentation.

    Returns ``(entries, method, confidence)``.  When segmentation is not trustworthy,
    an empty entry list is returned while the caller still retains the raw section.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    for pattern, method in (
        (NUMBERED_REFERENCE_START_RE, "numbered-punctuated"),
        (BARE_NUMBERED_REFERENCE_START_RE, "numbered-bare"),
    ):
        matches = list(pattern.finditer(normalized))
        markers: list[tuple[int, int]] = []
        for match in matches:
            number = _reference_marker_number(match)
            if number is not None:
                markers.append((match.start(), number))
        if not _markers_are_plausible(markers):
            continue

        entries: list[ReferenceEntry] = []
        usable_matches = [m for m in matches if _reference_marker_number(m) is not None]
        for index, match in enumerate(usable_matches):
            start = match.end()
            end = usable_matches[index + 1].start() if index + 1 < len(usable_matches) else len(normalized)
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
        if len(entries) >= 3:
            return tuple(entries), method, "HIGH"

    # Author-year bibliographies are deliberately not force-split yet.  A raw section
    # with many year anchors is still valuable evidence for a local AI/parser later.
    years = YEAR_RE.findall(normalized)
    if len(years) >= 3:
        return (), "raw-author-year-or-unsegmented", "MEDIUM"
    return (), "raw-unsegmented", "LOW"


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
        return None

    # The last exact heading in the latter 70% of a paper is usually the real
    # bibliography heading and avoids TOC/front-matter mentions of "References".
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

            found_emails = [m.group(1).lower() for m in EMAIL_RE.finditer(span.text)]
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
    """Read a local PDF and return deterministic evidence without changing the file.

    PDF-derived information is evidence, not Zotero metadata.  Failure is represented
    in the returned object so one bad or scanned PDF never blocks library ingestion.
    """
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

            page_count = int(doc.page_count)
            metadata = dict(doc.metadata or {})
            for page in doc:
                page_texts.append(page.get_text("text", sort=True) or "")
                raw_blocks = page.get_text("blocks", sort=True) or []
                text_blocks = [tuple(block) for block in raw_blocks if len(block) < 7 or block[6] == 0]
                blocks_by_page.append(text_blocks)
    except Exception as exc:  # backend-specific parse failures must be non-fatal
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
    references = find_reference_section(page_texts)

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
