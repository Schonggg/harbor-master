"""Strategy package exports."""

from harbormaster.court.strategies.label_synonym import LabelSynonymStrategy
from harbormaster.court.strategies.locode_map import LocodeMapStrategy
from harbormaster.court.strategies.numeric_extract import NumericExtractStrategy
from harbormaster.court.strategies.ocr_confusion import OcrConfusionStrategy
from harbormaster.court.strategies.ref_resolve import RefResolveStrategy
from harbormaster.court.strategies.suffix_strip import SuffixStripStrategy
from harbormaster.court.strategies.unit_convert import UnitConvertStrategy


def default_strategies() -> list:
    """Order matters: cheap deterministic first, OCR last."""
    return [
        SuffixStripStrategy(),
        LocodeMapStrategy(),
        UnitConvertStrategy(),
        RefResolveStrategy(),
        NumericExtractStrategy(),
        LabelSynonymStrategy(),
        OcrConfusionStrategy(),
    ]


__all__ = [
    "LabelSynonymStrategy",
    "LocodeMapStrategy",
    "NumericExtractStrategy",
    "OcrConfusionStrategy",
    "RefResolveStrategy",
    "SuffixStripStrategy",
    "UnitConvertStrategy",
    "default_strategies",
]
