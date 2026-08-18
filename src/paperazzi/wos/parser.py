"""Parser for Web of Science tagged plain-text Full Record exports."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

_TAG_RE = re.compile(r"^([A-Z0-9]{2})(?:\s(.*))?$")
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s;,\]\[<>]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(18|19|20|21)\d{2}\b")
_CORRESP_MARKER = "(corresponding author)"


def normalize_space(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split())


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = _DOI_RE.search(value)
    if not match:
        return None
    return match.group(0).rstrip(".);,").casefold()


def normalize_title(value: str | None) -> str | None:
    if not value:
        return None
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()) or None


def normalize_author_key(value: str | None) -> str | None:
    if not value:
        return None
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()) or None


@dataclass(slots=True)
class WosRawRecord:
    fields: dict[str, list[str]] = field(default_factory=dict)
    raw_text: str = ""

    def values(self, tag: str) -> list[str]:
        return list(self.fields.get(tag, ()))

    def text(self, tag: str) -> str | None:
        values = self.fields.get(tag)
        if not values:
            return None
        return normalize_space(" ".join(values))

    def first(self, tag: str) -> str | None:
        values = self.fields.get(tag)
        return normalize_space(values[0]) if values else None


@dataclass(slots=True, frozen=True)
class WosAuthor:
    order_index: int
    au_name: str
    full_name: str | None


@dataclass(slots=True, frozen=True)
class WosCorrespondenceGroup:
    order_index: int
    member_names: tuple[str, ...]
    address: str | None
    raw_group: str


@dataclass(slots=True, frozen=True)
class WosAddressGroup:
    order_index: int
    author_names: tuple[str, ...]
    address: str


@dataclass(slots=True, frozen=True)
class ParsedReference:
    order_index: int
    raw_text: str
    doi: str | None
    cited_author: str | None
    cited_year: int | None
    cited_source: str | None
    volume: str | None
    page: str | None


@dataclass(slots=True)
class ParsedWosRecord:
    ut: str
    doi: str | None
    title: str | None
    normalized_title: str | None
    source_title: str | None
    document_type: str | None
    abstract: str | None
    publication_year: int | None
    publication_date: str | None
    volume: str | None
    issue: str | None
    begin_page: str | None
    end_page: str | None
    article_number: str | None
    pmid: str | None
    times_cited_wos: int | None
    times_cited_total: int | None
    authors: list[WosAuthor]
    addresses: list[WosAddressGroup]
    organizations: list[str]
    correspondence_groups: list[WosCorrespondenceGroup]
    emails: list[str]
    researcher_ids: list[str]
    orcids: list[str]
    author_keywords: list[str]
    keywords_plus: list[str]
    classifications: dict[str, list[str]]
    funding_agencies: str | None
    funding_text: str | None
    references: list[ParsedReference]
    raw_record: WosRawRecord


def parse_tagged_text(text: str) -> list[WosRawRecord]:
    """Parse Clarivate WoS tagged plain text into complete raw records."""
    records: list[WosRawRecord] = []
    current: dict[str, list[str]] | None = None
    current_tag: str | None = None
    raw_lines: list[str] = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if current is None:
            if line.startswith("PT "):
                current = {}
                raw_lines = [line]
                current_tag = "PT"
                current.setdefault("PT", []).append(line[3:].strip())
            continue

        raw_lines.append(line)
        if line == "ER":
            records.append(WosRawRecord(fields=current, raw_text="\n".join(raw_lines)))
            current = None
            current_tag = None
            raw_lines = []
            continue
        if not line:
            continue
        if line[:1].isspace():
            if current_tag is not None:
                current[current_tag].append(line.strip())
            continue

        match = _TAG_RE.match(line)
        if match:
            current_tag = match.group(1)
            current.setdefault(current_tag, []).append((match.group(2) or "").strip())
        elif current_tag is not None:
            current[current_tag].append(line.strip())

    return records


def split_semicolon_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def parse_correspondence_groups(value: str | None) -> list[WosCorrespondenceGroup]:
    """Parse RP using WoS group-level `(corresponding author)` semantics.

    ``A; B (corresponding author), ADDRESS`` means both A and B are corresponding
    authors in one Corresponding Address group.  The marker does not modify only B.
    """
    if not value:
        return []
    raw_groups = re.split(r"\.\s*;\s*(?=[^.;]*?\(corresponding author\))", value, flags=re.I)
    groups: list[WosCorrespondenceGroup] = []
    for raw in raw_groups:
        part = raw.strip().strip(";")
        marker_pos = part.casefold().find(_CORRESP_MARKER)
        if marker_pos < 0:
            continue
        names_part = part[:marker_pos].strip().rstrip(" ,")
        tail = part[marker_pos + len(_CORRESP_MARKER):].strip()
        address = tail.lstrip(" ,").rstrip(" .") or None
        names = tuple(name.strip() for name in names_part.split(";") if name.strip())
        if names:
            groups.append(WosCorrespondenceGroup(len(groups), names, address, part))
    return groups


def parse_c1_groups(value: str | None) -> list[WosAddressGroup]:
    if not value:
        return []
    matches = list(re.finditer(r"\[([^\]]+)\]\s*(.*?)(?=;\s*\[|$)", value))
    if not matches:
        return [WosAddressGroup(0, (), value.strip())]
    groups: list[WosAddressGroup] = []
    for match in matches:
        names = tuple(x.strip() for x in match.group(1).split(";") if x.strip())
        address = match.group(2).strip().strip(";")
        groups.append(WosAddressGroup(len(groups), names, address))
    return groups


def parse_reference(raw: str, order_index: int) -> ParsedReference:
    doi = normalize_doi(raw)
    year_match = _YEAR_RE.search(raw)
    year = int(year_match.group(0)) if year_match else None
    pieces = [p.strip() for p in raw.split(",")]
    cited_author = pieces[0] if pieces else None
    cited_source = None
    if year_match:
        post = raw[year_match.end():].lstrip(" ,")
        cited_source = post.split(",", 1)[0].strip() or None
    vm = re.search(r"(?:^|,\s*)V([^,]+)", raw)
    pm = re.search(r"(?:^|,\s*)P([^,]+)", raw)
    return ParsedReference(
        order_index=order_index,
        raw_text=raw,
        doi=doi,
        cited_author=cited_author,
        cited_year=year,
        cited_source=cited_source,
        volume=vm.group(1).strip() if vm else None,
        page=pm.group(1).strip() if pm else None,
    )


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def interpret_record(raw: WosRawRecord) -> ParsedWosRecord:
    ut = raw.first("UT")
    if not ut:
        raise ValueError("WoS record is missing required UT accession number")
    au = raw.values("AU")
    af = raw.values("AF")
    authors = [
        WosAuthor(i, normalize_space(name) or name, normalize_space(af[i]) if i < len(af) else None)
        for i, name in enumerate(au)
    ]
    title = raw.text("TI")
    classifications = {
        tag: split_semicolon_values(raw.text(tag))
        for tag in ("WC", "SC", "TO", "WE")
        if raw.text(tag)
    }
    return ParsedWosRecord(
        ut=ut,
        doi=normalize_doi(raw.first("DI")),
        title=title,
        normalized_title=normalize_title(title),
        source_title=raw.text("SO"),
        document_type=raw.text("DT") or raw.first("PT"),
        abstract=raw.text("AB"),
        publication_year=_to_int(raw.first("PY")),
        publication_date=raw.text("PD"),
        volume=raw.first("VL"),
        issue=raw.first("IS"),
        begin_page=raw.first("BP"),
        end_page=raw.first("EP"),
        article_number=raw.first("AR"),
        pmid=raw.first("PM"),
        times_cited_wos=_to_int(raw.first("TC")),
        times_cited_total=_to_int(raw.first("Z9")),
        authors=authors,
        addresses=parse_c1_groups(raw.text("C1")),
        organizations=split_semicolon_values(raw.text("C3")),
        correspondence_groups=parse_correspondence_groups(raw.text("RP")),
        emails=split_semicolon_values(raw.text("EM")),
        researcher_ids=split_semicolon_values(raw.text("RI")),
        orcids=split_semicolon_values(raw.text("OI")),
        author_keywords=split_semicolon_values(raw.text("DE")),
        keywords_plus=split_semicolon_values(raw.text("ID")),
        classifications=classifications,
        funding_agencies=raw.text("FU"),
        funding_text=raw.text("FX"),
        references=[parse_reference(value, i) for i, value in enumerate(raw.values("CR"))],
        raw_record=raw,
    )


def parse_records(text: str) -> list[ParsedWosRecord]:
    return [interpret_record(record) for record in parse_tagged_text(text)]
