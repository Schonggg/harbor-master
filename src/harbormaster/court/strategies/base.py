"""Defense strategy protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from harbormaster.models import Charge, Plea


@runtime_checkable
class Strategy(Protocol):
    name: str

    def try_defend(self, charge: Charge) -> Plea:
        """Return Plea with accepted=True if the charge is neutralized."""
        ...
