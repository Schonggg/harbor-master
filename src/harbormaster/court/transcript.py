"""Court transcript — data source for Bridge court animation."""

from __future__ import annotations

from harbormaster.models import Charge, CourtTranscript, FieldVerdict, Plea


class TranscriptWriter:
    def __init__(self, transcript: CourtTranscript) -> None:
        self.transcript = transcript

    def charge(self, charge: Charge) -> None:
        self.transcript.add(
            "charge",
            charge.field,
            {
                "left": charge.left.raw_value,
                "right": charge.right.raw_value,
                "note": charge.note,
            },
        )

    def plea(self, field: str, plea: Plea) -> None:
        self.transcript.add(
            "plea",
            field,
            {
                "strategy": plea.strategy,
                "accepted": plea.accepted,
                "argument": plea.argument,
                "transformed_left": plea.transformed_left,
                "transformed_right": plea.transformed_right,
            },
        )

    def verdict(self, fv: FieldVerdict) -> None:
        self.transcript.add(
            "verdict",
            fv.field,
            {
                "state": fv.state.value,
                "winning_strategy": fv.winning_strategy,
                "rationale": fv.rationale,
                "exposure_usd": fv.exposure_usd,
            },
        )
