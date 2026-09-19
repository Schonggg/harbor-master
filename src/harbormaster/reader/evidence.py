"""Evidence helpers."""

from __future__ import annotations

from harbormaster.models import Evidence, EvidenceSource


def make_evidence(
    snippet: str,
    source: EvidenceSource = EvidenceSource.TEXT,
    page: int | None = 1,
    doc_id: str | None = None,
    attachment_name: str | None = None,
) -> Evidence:
    return Evidence(
        raw_text=snippet,
        snippet=snippet[:120],
        page=page,
        source=source,
        doc_id=doc_id,
        attachment_name=attachment_name,
    )
