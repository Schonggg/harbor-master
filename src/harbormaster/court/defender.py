"""Defender — try strategies in order until one plea is accepted."""

from __future__ import annotations

from harbormaster.court.strategies import default_strategies
from harbormaster.models import Charge, Plea


class Defender:
    def __init__(self, strategies: list | None = None) -> None:
        self.strategies = strategies or default_strategies()

    def defend(self, charge: Charge) -> list[Plea]:
        pleas: list[Plea] = []
        for strategy in self.strategies:
            plea = strategy.try_defend(charge)
            pleas.append(plea)
            if plea.accepted:
                break
        return pleas
