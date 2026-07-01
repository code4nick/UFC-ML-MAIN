from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LifetimeRecord:
    wins: int
    losses: int
    pending: int
    pushes: int
    units: float

    @property
    def decided(self) -> int:
        return self.wins + self.losses

    @property
    def hit_rate(self) -> float | None:
        if self.decided == 0:
            return None
        return self.wins / self.decided


def units_for_result(won: bool, american_odds: int | None) -> float:
    """Units won/lost on a 1u risk bet."""
    if not won:
        return -1.0
    if american_odds is None:
        return 100.0 / 110.0
    if american_odds > 0:
        return american_odds / 100.0
    return 100.0 / abs(american_odds)


def grade_pick(pick_fighter_id: int, winner_id: int | None) -> tuple[str, float | None]:
    if winner_id is None:
        return "pending", None
    if pick_fighter_id == winner_id:
        return "win", None
    return "loss", None
