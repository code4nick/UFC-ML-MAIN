from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.db.connection import get_connection, init_db
from src.db.repository import Repository
from src.engine.math_engine import predict_fight
from src.engine.research import blend_prediction
from src.services.card_loader import FightAnalysis
from src.services.fighter_pool import build_prediction_pool


@dataclass
class CompareResult:
    analysis: FightAnalysis
    pool_size: int
    pool_label: str
    red_missing: list[str]
    blue_missing: list[str]


def compare_fighters(
    db_path: Path | None = None,
    *,
    red_fighter_id: int,
    blue_fighter_id: int,
    weight_class: str | None = None,
    pool_mode: str = "weight_class",
    title_fight: bool = False,
    scheduled_rounds: int = 3,
) -> CompareResult:
    if red_fighter_id == blue_fighter_id:
        raise ValueError("Select two different fighters.")

    init_db(db_path)
    with get_connection(db_path) as conn:
        repo = Repository(conn)
        fighters = repo.list_fighters_with_stats()
        if not fighters:
            raise ValueError("No fighter stats in database. Run ingest first.")

        by_id = {f["fighter_id"]: f for f in fighters}
        if red_fighter_id not in by_id or blue_fighter_id not in by_id:
            raise ValueError("One or both fighters have no stats. Re-ingest or pick different fighters.")

        red_row = by_id[red_fighter_id]
        blue_row = by_id[blue_fighter_id]
        wc_map = repo.get_latest_weight_classes()

        display_wc = weight_class or wc_map.get(red_fighter_id) or wc_map.get(blue_fighter_id)
        pool = build_prediction_pool(
            repo,
            display_wc,
            required_ufcstats_ids=[red_row["ufcstats_id"], blue_row["ufcstats_id"]],
            full_roster_only=(pool_mode == "full_roster"),
        )

        rounds = 5 if title_fight else scheduled_rounds
        math_pred = predict_fight(
            red_id=red_row["ufcstats_id"],
            blue_id=blue_row["ufcstats_id"],
            red_name=red_row["name"],
            blue_name=blue_row["name"],
            fighter_stats=pool.fighter_stats,
            weight_classes=pool.weight_classes,
            fight_id=0,
            weight_class=display_wc,
            pool_by_weight_class=True,
            scheduled_rounds=rounds,
            is_title_fight=title_fight,
        )

        red_ctx = repo.get_latest_context_for_fighter(red_fighter_id)
        blue_ctx = repo.get_latest_context_for_fighter(blue_fighter_id)
        if title_fight:
            red_ctx = {**red_ctx, "is_title_fight": True, "scheduled_rounds": 5}
            blue_ctx = {**blue_ctx, "is_title_fight": True, "scheduled_rounds": 5}

        blended = blend_prediction(math_pred, red_ctx, blue_ctx)

        analysis = FightAnalysis(
            fight_id=0,
            red_name=red_row["name"],
            blue_name=blue_row["name"],
            weight_class=display_wc,
            blended=blended,
            polymarket=None,
            red_context=red_ctx,
            blue_context=blue_ctx,
        )

        return CompareResult(
            analysis=analysis,
            pool_size=pool.size,
            pool_label=pool.label,
            red_missing=red_row["missing"],
            blue_missing=blue_row["missing"],
        )
