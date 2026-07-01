from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import DEFAULT_ROSTER_CARDS, MAX_ROSTER_CARDS, ROSTER_CARD_STEP
from src.db.repository import Repository
from src.services.pool_limits import min_pool_for_division
from src.services.weight_class import normalize_weight_class


@dataclass
class PredictionPool:
    fighter_stats: dict[str, dict[str, Any]]
    weight_classes: dict[str, str | None]
    label: str
    size: int


def _same_division(a: str | None, b: str | None) -> bool:
    na, nb = normalize_weight_class(a), normalize_weight_class(b)
    return na is not None and na == nb


def _division_fighters(
    all_fighters: list[dict[str, Any]],
    wc_map: dict[int, str | None],
    target_wc: str,
) -> list[dict[str, Any]]:
    return [
        f
        for f in all_fighters
        if _same_division(wc_map.get(f["fighter_id"]), target_wc)
    ]


def _fighters_in_card_window(
    repo: Repository,
    full_roster: list[dict[str, Any]],
    card_window: int,
) -> tuple[list[dict[str, Any]], str]:
    recent_ids = repo.get_fighter_ids_from_recent_events(card_window)
    if not recent_ids:
        return full_roster, ""
    filtered = [f for f in full_roster if f["fighter_id"] in recent_ids]
    n_events = len(repo.get_pool_event_ids(card_window))
    return filtered, f"Last {n_events} cards · "


def build_prediction_pool(
    repo: Repository,
    bout_weight_class: str | None,
    *,
    required_ufcstats_ids: list[str],
    full_roster_only: bool = False,
    roster_card_window: int | None = DEFAULT_ROSTER_CARDS,
) -> PredictionPool:
    """Build percentile pool from division fighters in DB (bout weight class)."""
    full_roster = repo.list_fighters_with_stats()
    if not full_roster:
        raise ValueError("No fighter stats in database. Run ingest first.")

    by_ufc = {f["ufcstats_id"]: f for f in full_roster}
    wc_map = repo.get_latest_weight_classes()
    target_wc = normalize_weight_class(bout_weight_class)

    if full_roster_only or not target_wc:
        pool = list(full_roster)
        label = f"Full roster · {len(pool)} fighters"
    else:
        min_pool = min_pool_for_division(target_wc)
        division: list[dict[str, Any]] = []
        window_label = ""
        cards_used = roster_card_window or DEFAULT_ROSTER_CARDS

        if roster_card_window:
            start = roster_card_window
            cap = MAX_ROSTER_CARDS
            while cards_used <= cap:
                scoped, window_label = _fighters_in_card_window(
                    repo, full_roster, cards_used
                )
                division = _division_fighters(scoped, wc_map, target_wc)
                if len(division) >= min_pool:
                    break
                if cards_used >= cap:
                    break
                cards_used = min(cards_used + ROSTER_CARD_STEP, cap)
        else:
            division = _division_fighters(full_roster, wc_map, target_wc)

        if len(division) < min_pool:
            raise ValueError(
                f"Only {len(division)} fighters in {target_wc} pool "
                f"(need {min_pool}+; tried up to {cards_used} cards). "
                "Run `python -m src.ingest --last-cards --refresh` to add more cards."
            )
        pool = division
        label = f"{window_label}{target_wc} division · {len(pool)} fighters"

    pool_ids = {f["ufcstats_id"] for f in pool}
    for ufc_id in required_ufcstats_ids:
        if ufc_id and ufc_id not in pool_ids:
            if ufc_id in by_ufc:
                pool.append(by_ufc[ufc_id])
                pool_ids.add(ufc_id)
            else:
                raise ValueError(
                    f"Fighter {ufc_id} has no stats in the database. "
                    "Run `python -m src.ingest --upcoming` to refresh this card."
                )

    fighter_stats: dict[str, dict[str, Any]] = {}
    weight_classes: dict[str, str | None] = {}
    for entry in pool:
        key = entry["ufcstats_id"]
        fighter_stats[key] = entry["stats"]
        weight_classes[key] = target_wc or normalize_weight_class(wc_map.get(entry["fighter_id"]))

    return PredictionPool(
        fighter_stats=fighter_stats,
        weight_classes=weight_classes,
        label=label,
        size=len(pool),
    )
