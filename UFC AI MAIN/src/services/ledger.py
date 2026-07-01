from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.db.connection import get_connection, init_db
from src.db.repository import Repository, utc_now_iso
from src.engine.betting import analyze_bet
from src.engine.grading import LifetimeRecord, units_for_result
from src.services.card_loader import (
    FightAnalysis,
    get_fight_market_lines,
    load_card_predictions,
    load_merged_odds,
)


@dataclass
class LogResult:
    logged: int
    skipped: int
    event_name: str


def _pick_fighter_id(analysis: FightAnalysis, fights: list[dict[str, Any]]) -> int | None:
    fight = next((f for f in fights if int(f["fight_id"]) == analysis.fight_id), None)
    if not fight:
        return None
    if analysis.blended.pick_corner == "red":
        return int(fight["red_id"])
    return int(fight["blue_id"])


def log_card_picks(
    db_path: Path | None = None,
    event_name: str | None = None,
    *,
    bankroll: float = 1000.0,
) -> LogResult:
    """Lock predictions to the ledger before the card (one row per fight)."""
    card = load_card_predictions(db_path, event_name=event_name, use_polymarket=True)
    yaml_odds = load_merged_odds()
    logged_at = utc_now_iso()
    event_id = int(card.event["id"])

    init_db(db_path)
    logged = skipped = 0

    with get_connection(db_path) as conn:
        repo = Repository(conn)
        for analysis in card.analyses:
            if repo.prediction_exists_for_fight(analysis.fight_id):
                skipped += 1
                continue

            pick_fighter_id = _pick_fighter_id(analysis, card.fights)
            if pick_fighter_id is None:
                skipped += 1
                continue

            blended = analysis.blended
            red_ml, blue_ml, red_imp, blue_imp, source = get_fight_market_lines(analysis, yaml_odds)
            pick_imp = red_imp if blended.pick_corner == "red" else blue_imp
            bet = analyze_bet(
                blended.pick_corner,
                blended.pick_name,
                blended.win_prob,
                blended.tier,
                red_ml,
                blue_ml,
                bankroll=bankroll,
                market_implied=pick_imp,
                market_source=source,
            )

            repo.insert_prediction(
                fight_id=analysis.fight_id,
                event_id=event_id,
                pick_fighter_id=pick_fighter_id,
                pick_name=blended.pick_name,
                pick_corner=blended.pick_corner,
                math_prob=blended.math_win_prob,
                final_prob=blended.win_prob,
                tier=blended.tier,
                market_implied=bet.vegas_implied,
                market_source=bet.market_source,
                edge_points=bet.edge_points,
                bet_verdict=bet.verdict,
                pick_ml=bet.pick_ml,
                kelly_stake=bet.half_kelly_stake,
                logged_at=logged_at,
            )
            logged += 1
        conn.commit()

    return LogResult(logged=logged, skipped=skipped, event_name=card.event["name"])


def grade_pending(
    db_path: Path | None = None,
    event_name: str | None = None,
) -> int:
    """Grade pending predictions using fight results in the database."""
    init_db(db_path)
    graded = 0
    with get_connection(db_path) as conn:
        repo = Repository(conn)
        pending = repo.get_pending_predictions(event_name=event_name)
        for pred in pending:
            fight = repo.get_fight_result(int(pred["fight_id"]))
            if not fight or fight.get("winner_id") is None:
                continue

            winner_id = int(fight["winner_id"])
            status = "win" if winner_id == int(pred["pick_fighter_id"]) else "loss"
            units = units_for_result(status == "win", pred.get("pick_ml"))
            winner_name = fight.get("winner_name") or "Unknown"

            repo.grade_prediction(
                prediction_id=int(pred["id"]),
                status=status,
                units=units,
                winner_name=winner_name,
                method=fight.get("method"),
                graded_at=utc_now_iso(),
            )
            graded += 1
        conn.commit()
    return graded


def get_lifetime_record(db_path: Path | None = None) -> LifetimeRecord:
    init_db(db_path)
    with get_connection(db_path) as conn:
        return Repository(conn).get_lifetime_record()


def get_graded_predictions(
    db_path: Path | None = None,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        return Repository(conn).get_graded_predictions(limit=limit)
