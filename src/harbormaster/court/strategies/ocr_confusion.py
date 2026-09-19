"""OCR confusion pairs — ONLY when evidence.source is ocr/vision.

ADR-003: never apply to clean text-layer extracts.
"""

from __future__ import annotations

from harbormaster.models import Charge, EvidenceSource, Plea

# Common OCR confusions in shipping docs
_CONFUSIONS = (
    ("0", "O"),
    ("1", "I"),
    ("1", "L"),
    ("5", "S"),
    ("8", "B"),
    ("2", "Z"),
    ("RN", "M"),
    ("VV", "W"),
)


def _from_ocr(charge: Charge) -> bool:
    sources = {charge.left.evidence.source, charge.right.evidence.source}
    return bool(sources & {EvidenceSource.OCR, EvidenceSource.VISION})


def _normalize_ocr(text: str) -> str:
    t = text.upper().strip()
    t = " ".join(t.split())
    for a, b in _CONFUSIONS:
        t = t.replace(a, b)
    return t


class OcrConfusionStrategy:
    name = "ocr_confusion"

    def try_defend(self, charge: Charge) -> Plea:
        if not _from_ocr(charge):
            return Plea(
                strategy=self.name,
                accepted=False,
                argument="guardrail: source is not ocr/vision",
                confidence=0.0,
            )
        left = _normalize_ocr(charge.left.raw_value)
        right = _normalize_ocr(charge.right.raw_value)
        ok = bool(left) and left == right
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"ocr-normalized: '{left}' vs '{right}'",
            transformed_left=left,
            transformed_right=right,
            confidence=0.85 if ok else 0.0,
        )
