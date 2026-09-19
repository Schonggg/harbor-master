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
        r"(?:Shipper(?:\s*/\s*Exporter)?|Consignor|Exporter)[:\s]+(.+)", re.I
    ),
    "consignee": re.compile(r"Consignee[:\s]+(.+)", re.I),
    "notify_party": re.compile(r"Notify(?:\s+Party)?[:\s]+(.+)", re.I),
    "port_of_loading": re.compile(
        r"(?:Port of Loading|Load Port|Place of Loading|\bPOL\b)[:\s]+(.+)", re.I
    ),
    "port_of_discharge": re.compile(
        r"(?:Port of Discharge|Discharge Port|Place of Discharge|\bPOD\b)[:\s]+(.+)", re.I
    ),
    "container_count": re.compile(
        r"(?:No\.?\s*of\s*(?:Containers|Pkgs|Packages)(?:\s+or\s+Packages)?|Container Count|Containers|Quantity)[:\s]+(.+)",
        re.I,
    ),
    "gross_weight_kg": re.compile(
        r"(?:Gross\s*Weight(?:\s*\(\s*KG[s]?\s*\))?|Gross\s*Wt(?:\s*\(\s*kgs?\s*\))?|G\.?W\.?|Gr\.?\s*Wt)[:\s]+(.+)",
        re.I,
    ),
    "vessel_voyage": re.compile(
        r"(?:Vessel(?:\s*/\s*Voyage)?|Vessel Name|Ocean Vessel)[:\s]+(.+)", re.I
    ),
}

_LINE_RE = re.compile(r"^([^:\n]{2,40})[:\-]\s*(.+)$")


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
            raw = match.group(1).strip().splitlines()[0].strip()
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
        for line in text.splitlines():
            match = _LINE_RE.match(line.strip())
            if not match:
                continue
            label = _norm_label(match.group(1))
            canonical = index.get(label)
            if not canonical:
                continue
            raw = match.group(2).strip()
            if not raw:
                continue
            out.setdefault(
                canonical,
                FieldValue(
                    name=canonical,
                    raw_value=raw,
                    confidence=0.93,
                    evidence=make_evidence(raw, source=source, attachment_name=attachment_name),
                ),
            )
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
                raw = str(item.get("raw_value") or "").strip()
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
