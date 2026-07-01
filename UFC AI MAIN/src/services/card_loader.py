from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import CONFIG_DIR, DEFAULT_DB_PATH, load_yaml
from src.db.connection import get_connection, init_db
from src.db.repository import Repository
from src.engine.math_engine import FightPrediction, predict_fight
from src.engine.research import BlendedPrediction, blend_prediction
from src.odds.polymarket import PolymarketLine, fetch_card_lines, match_line_to_fight
from src.services.fighter_pool import build_prediction_pool
from src.services.weight_class import normalize_weight_class


@dataclass
class FightAnalysis:
    fight_id: int
    red_name: str
    blue_name: str
    weight_class: str | None
    blended: BlendedPrediction
    polymarket: PolymarketLine | None
    red_context: dict[str, Any]
    blue_context: dict[str, Any]


@dataclass
class CardData:
    event: dict[str, Any]
    fights: list[dict[str, Any]]
    predictions: list[FightPrediction]
    analyses: list[FightAnalysis]


def _polymarket_query(event: dict[str, Any]) -> str:
    name = event.get("name") or "UFC"
    if "UFC" in name.upper():
        parts = name.split(":")
        return parts[0].strip() if parts else name
    return name


def load_card_predictions(
    db_path: Path | None = None,
    event_name: str | None = None,
    *,
    use_polymarket: bool = True,
) -> CardData:
    init_db(db_path)
    with get_connection(db_path) as conn:
        repo = Repository(conn)
        if event_name:
            event = repo.get_event_by_name(event_name)
        else:
            event = repo.get_upcoming_event() or repo.get_latest_event()
        if not event:
            raise ValueError("No event found in database. Run ingest first.")

        event_id = int(event["id"])
        fights = repo.get_event_fights(event_id)
        contexts = repo.get_latest_contexts_for_event(event_id)
        if not fights:
            raise ValueError(f"No fights found for event: {event['name']}")

        poly_lines: list[PolymarketLine] = []
        if use_polymarket:
            try:
                poly_lines = fetch_card_lines(_polymarket_query(event))
            except Exception:
                poly_lines = []

        predictions: list[FightPrediction] = []
        analyses: list[FightAnalysis] = []

        for fight in fights:
            red_key = fight["red_ufcstats_id"]
            blue_key = fight["blue_ufcstats_id"]
            if not red_key or not blue_key:
                continue

            bout_wc = normalize_weight_class(fight.get("weight_class"))
            pool = build_prediction_pool(
                repo,
                bout_wc,
                required_ufcstats_ids=[red_key, blue_key],
            )

            math_pred = predict_fight(
                red_id=red_key,
                blue_id=blue_key,
                red_name=fight["red_name"],
                blue_name=fight["blue_name"],
                fighter_stats=pool.fighter_stats,
                weight_classes=pool.weight_classes,
                fight_id=int(fight["fight_id"]),
                weight_class=fight.get("weight_class"),
                pool_by_weight_class=True,
                scheduled_rounds=int(fight.get("scheduled_rounds") or 3),
                is_title_fight=bool(fight.get("is_title_fight")),
            )
            predictions.append(math_pred)

            red_ctx = contexts.get((int(fight["fight_id"]), int(fight["red_id"])), {})
            blue_ctx = contexts.get((int(fight["fight_id"]), int(fight["blue_id"])), {})
            blended = blend_prediction(math_pred, red_ctx, blue_ctx)
            poly = match_line_to_fight(fight["red_name"], fight["blue_name"], poly_lines)

            analyses.append(
                FightAnalysis(
                    fight_id=int(fight["fight_id"]),
                    red_name=fight["red_name"],
                    blue_name=fight["blue_name"],
                    weight_class=fight.get("weight_class"),
                    blended=blended,
                    polymarket=poly,
                    red_context=red_ctx,
                    blue_context=blue_ctx,
                )
            )

        return CardData(event=event, fights=fights, predictions=predictions, analyses=analyses)


def _name_key(name: str) -> str:
    return name.lower().strip()


def load_odds_file(path: Path) -> dict[str, dict[str, int | None]]:
    data = load_yaml(path)
    result: dict[str, dict[str, int | None]] = {}
    for fight in data.get("fights", []):
        red = fight.get("red_name", "")
        blue = fight.get("blue_name", "")
        key = f"{_name_key(red)}|{_name_key(blue)}"
        result[key] = {
            "red_ml": fight.get("red_ml"),
            "blue_ml": fight.get("blue_ml"),
        }
    return result


def find_odds_for_fight(
    red_name: str,
    blue_name: str,
    odds_map: dict[str, dict[str, int | None]],
) -> tuple[int | None, int | None]:
    key = f"{_name_key(red_name)}|{_name_key(blue_name)}"
    rev = f"{_name_key(blue_name)}|{_name_key(red_name)}"
    if key in odds_map:
        o = odds_map[key]
        return o.get("red_ml"), o.get("blue_ml")
    if rev in odds_map:
        o = odds_map[rev]
        return o.get("blue_ml"), o.get("red_ml")
    return None, None


def get_fight_market_lines(
    analysis: FightAnalysis,
    yaml_odds: dict[str, dict[str, int | None]] | None = None,
) -> tuple[int | None, int | None, float | None, float | None, str]:
    """Return red_ml, blue_ml, red_implied, blue_implied, source label."""
    if analysis.polymarket:
        p = analysis.polymarket
        return p.red_ml, p.blue_ml, p.red_prob, p.blue_prob, "Polymarket"

    if yaml_odds:
        red_ml, blue_ml = find_odds_for_fight(analysis.red_name, analysis.blue_name, yaml_odds)
        if red_ml is not None or blue_ml is not None:
            from src.engine.betting import american_to_implied_prob

            red_imp = american_to_implied_prob(red_ml) if red_ml is not None else None
            blue_imp = american_to_implied_prob(blue_ml) if blue_ml is not None else None
            return red_ml, blue_ml, red_imp, blue_imp, "Sportsbook (config)"

    return None, None, None, None, "none"


def discover_odds_files() -> list[Path]:
    odds_dir = CONFIG_DIR / "odds"
    if not odds_dir.exists():
        return []
    return sorted(odds_dir.glob("*.yaml"))


def load_merged_odds(extra_path: Path | None = None) -> dict[str, dict[str, int | None]]:
    merged: dict[str, dict[str, int | None]] = {}
    for path in discover_odds_files():
        merged.update(load_odds_file(path))
    if extra_path and extra_path.exists():
        merged.update(load_odds_file(extra_path))
    return merged
