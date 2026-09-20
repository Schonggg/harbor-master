"""LLM structured extraction → FieldValue map. Regex/alias fallback is always on."""

from __future__ import annotations

import re
from pathlib import Path

from harbormaster.config import get_field_aliases, load_prompt
from harbormaster.llm.client import get_llm_client, llm_available
from harbormaster.models import (
    COMPARE_FIELDS,
    EvidenceSource,
    ExtractedDocument,
    FieldValue,
    canonical_field_name,
)
from harbormaster.reader.detector import select_parser
from harbormaster.reader.evidence import make_evidence
from harbormaster.reader.health_check import classify_doc_kind
from harbormaster.reader.parsers.base import BaseParser

_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "shipper": re.compile(
        r"(?:Shipper(?:\s*/\s*Exporter)?|Consignor|Exporter)[ \t:]+(.+)", re.I
    ),
    "consignee": re.compile(r"Consignee[ \t:]+(.+)", re.I),
    "notify_party": re.compile(r"Notify(?:\s+Party)?[ \t:]+(.+)", re.I),
    "port_of_loading": re.compile(
        r"(?:Port of Loading|Load Port|Place of Loading|\bPOL\b)(?:\s*\(\s*POL\s*\))?[ \t:]+(.+)",
        re.I,
    ),
    "port_of_discharge": re.compile(
        r"(?:Port of Discharge|Discharge Port|Place of Discharge|\bPOD\b)(?:\s*\(\s*POD\s*\))?[ \t:]+(.+)",
        re.I,
    ),
    "container_count": re.compile(
        r"(?:No\.?\s*of\s*(?:Containers|Pkgs|Packages)(?:\s+or\s+Packages)?|Container Count|Containers|Quantity)[ \t:]+(.+)",
        re.I,
    ),
    "gross_weight_kg": re.compile(
        r"(?:Gross\s*Weight[^\n:]{0,24}|Gross\s*Wt(?:\s*\(\s*kgs?\s*\))?|G\.?W\.?|Gr\.?\s*Wt)[ \t]*:[ \t]*(.+)",
        re.I,
    ),
    "vessel_voyage": re.compile(
        r"(?:Vessel(?:\s*/\s*Voyage)?|Vessel Name|Ocean Vessel)[ \t:]+(.+)", re.I
    ),
}

_LINE_RE = re.compile(r"^([^:\n]{2,40})[:\-]\s*(.+)$")
_POL_POD_PREFIX = re.compile(r"^\(\s*(?:POL|POD)\s*\)\s*:?\s*", re.I)
_ROLE_PREFIX = re.compile(
    r"^(?:notify(?:\s+party)?|consignee|shipper|name|voyage|vessel(?:\s*/\s*voyage)?)\s*:\s*",
    re.I,
)
_VOYAGE_LINE = re.compile(r"^(?:voyage(?:\s*(?:no\.?|number))?|voy\.?)\s*:?\s*(.+)$", re.I)
_HAS_VOYAGE = re.compile(r"(?:\bV\.\w+|\s/\s*\S+$)", re.I)


def _clean_extracted(name: str, raw: str, text: str = "") -> str:
    value = (raw or "").strip()
    if name in {"port_of_loading", "port_of_discharge"}:
        value = _POL_POD_PREFIX.sub("", value).strip()
    value = _ROLE_PREFIX.sub("", value).strip()
    if name == "vessel_voyage":
        value = _attach_voyage(text, value)
    return value


def _attach_voyage(text: str, raw: str) -> str:
    value = (raw or "").strip()
    if not value or _HAS_VOYAGE.search(value):
        return value
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if value not in line:
            continue
        if i + 1 >= len(lines):
            break
        hit = _VOYAGE_LINE.match(lines[i + 1])
        if hit:
            voy = hit.group(1).strip()
            if voy and voy.upper() not in value.upper():
                return f"{value} {voy}"
        break
    return value


class FieldExtractor:
    def __init__(self, degrade: bool = False, rules_only: bool = False) -> None:
        self.degrade = degrade
        self.rules_only = rules_only
        self.prompt = load_prompt("extract_fields.md")

    def extract_path(self, path: Path, doc_id: str | None = None) -> ExtractedDocument:
        parser: BaseParser = select_parser(path)
        text, page_count = _parse_with_meta(parser, path)
        source = (
            EvidenceSource.VISION
            if parser.name == "vision"
            else EvidenceSource.OCR
            if parser.name in {"ocr", "vision"}
            else EvidenceSource.TEXT
        )
        fields = self._regex_extract(text, source, path.name)
        fields.update(self._alias_extract(text, source, path.name))
        if not self.degrade and not self.rules_only and llm_available():
            fields.update(self._llm_extract(text, source, path.name))
        doc = ExtractedDocument(
            doc_id=doc_id or path.stem,
            filename=path.name,
            fields=_mirror_weight(fields),
            parser_used=parser.name,
            degraded=self.degrade or self.rules_only or not llm_available(),
            text=text,
            page_count=page_count,
        )
        doc.kind = classify_doc_kind(doc)  # type: ignore[assignment]
        return doc

    def extract_text(
        self,
        text: str,
        filename: str = "inline.txt",
        source: EvidenceSource = EvidenceSource.EMAIL_BODY,
    ) -> ExtractedDocument:
        fields = self._regex_extract(text, source, filename)
        fields.update(self._alias_extract(text, source, filename))
        if not self.degrade and not self.rules_only and llm_available() and len(text.strip()) > 40:
            fields.update(self._llm_extract(text, source, filename))
        doc = ExtractedDocument(
            filename=filename,
            fields=_mirror_weight(fields),
            parser_used="text",
            degraded=self.degrade or self.rules_only or not llm_available(),
            text=text,
        )
        doc.kind = classify_doc_kind(doc)  # type: ignore[assignment]
        return doc

    def _regex_extract(
        self, text: str, source: EvidenceSource, attachment_name: str
    ) -> dict[str, FieldValue]:
        out: dict[str, FieldValue] = {}
        for name, pattern in _FIELD_PATTERNS.items():
            match = pattern.search(text)
            if not match:
                continue
            raw = _clean_extracted(name, match.group(1) or "", text)
            if not raw:
                continue
            raw = raw.splitlines()[0].strip()
            raw = _clean_extracted(name, raw, text)
            if not raw:
                continue
            out[name] = FieldValue(
                name=name,
                raw_value=raw,
                confidence=0.96,
                evidence=make_evidence(raw, source=source, attachment_name=attachment_name),
            )
        return out

    def _alias_extract(
        self, text: str, source: EvidenceSource, attachment_name: str
    ) -> dict[str, FieldValue]:
        aliases = get_field_aliases()
        index: dict[str, str] = {}
        for canonical, names in aliases.items():
            index[_norm_label(canonical)] = canonical
            for alias in names:
                index[_norm_label(alias)] = canonical
        out: dict[str, FieldValue] = {}

        def _put(canonical: str, raw: str) -> None:
            raw = _clean_extracted(canonical, raw, text)
            if not raw:
                return
            out.setdefault(
                canonical,
                FieldValue(
                    name=canonical,
                    raw_value=raw,
                    confidence=0.93,
                    evidence=make_evidence(raw, source=source, attachment_name=attachment_name),
                ),
            )

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            match = _LINE_RE.match(line)
            if match:
                canonical = index.get(_norm_label(match.group(1)))
                if canonical:
                    _put(canonical, match.group(2))
                continue
            canonical = index.get(_norm_label(line))
            if not canonical or i + 1 >= len(lines):
                continue
            nxt = lines[i + 1]
            if re.match(r"^[^:\n]{2,40}:\s+\S", nxt) or index.get(_norm_label(nxt)):
                continue
            if canonical in {"gross_weight_kg", "gross_weight", "container_count"} and not re.match(
                r"\d", nxt
            ):
                continue
            _put(canonical, nxt)
        return out

    def _llm_extract(
        self, text: str, source: EvidenceSource, attachment_name: str
    ) -> dict[str, FieldValue]:
        try:
            client = get_llm_client()
            data = client.cached_json(
                "extract",
                text[:12000],
                [
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": text[:12000]},
                ],
            )
            out: dict[str, FieldValue] = {}
            for item in data.get("fields", []):
                name = canonical_field_name(str(item.get("name", "")))
                raw = _clean_extracted(name, str(item.get("raw_value") or "").strip(), text)
                if not name or not raw:
                    continue
                evidence = item.get("evidence") or {}
                page = evidence.get("page")
                snippet = evidence.get("snippet") or raw
                out[name] = FieldValue(
                    name=name,
                    raw_value=raw,
                    normalized=item.get("normalized_hint"),
                    confidence=float(item.get("confidence", 0.8)),
                    evidence=make_evidence(
                        snippet,
                        source=source,
                        page=int(page) if page else 1,
                        attachment_name=attachment_name,
                    ),
                )
            return out
        except Exception:
            return {}


def _norm_label(label: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", label.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_with_meta(parser: BaseParser, path: Path) -> tuple[str, int]:
    parse_pages = getattr(parser, "parse_pages", None)
    if callable(parse_pages):
        try:
            pages = parse_pages(path)
            if isinstance(pages, list):
                texts = []
                for i, page in enumerate(pages, start=1):
                    if isinstance(page, dict):
                        texts.append(page.get("text") or "")
                    else:
                        texts.append(str(page))
                return "\n".join(texts), len(pages)
        except Exception:
            pass
    try:
        return parser.parse(path), 0
    except Exception:
        return "", 0


def _mirror_weight(fields: dict[str, FieldValue]) -> dict[str, FieldValue]:
    """Keep both gross_weight and gross_weight_kg populated when either is found."""
    gw = fields.get("gross_weight_kg") or fields.get("gross_weight")
    if gw:
        kg = gw.model_copy(update={"name": "gross_weight_kg"})
        legacy = gw.model_copy(update={"name": "gross_weight"})
        fields["gross_weight_kg"] = kg
        fields["gross_weight"] = legacy
    return fields


def official_fields(doc: ExtractedDocument) -> dict[str, FieldValue]:
    out: dict[str, FieldValue] = {}
    for name in COMPARE_FIELDS:
        fv = doc.fields.get(name)
        if name == "gross_weight_kg" and fv is None:
            fv = doc.fields.get("gross_weight")
        if fv:
            out[name] = fv.model_copy(update={"name": name})
    return out
