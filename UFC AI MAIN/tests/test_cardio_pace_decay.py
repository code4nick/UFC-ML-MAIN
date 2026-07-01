"""Unit tests for pace-decay cardio metrics."""

from __future__ import annotations

from src.engine.math_engine import _cardio_category_weight, predict_fight
from src.scrapers.derived_stats import compute_derived_stats


def _neutral_stats(**overrides: float) -> dict[str, float]:
    base = {
        "slpm": 50.0,
        "str_acc": 50.0,
        "str_def": 50.0,
        "kd_per_fight": 50.0,
        "td_avg": 50.0,
        "td_acc": 50.0,
        "td_def": 50.0,
        "sub_avg": 50.0,
        "ctrl_time_per_fight_seconds": 50.0,
        "reversals_per_fight": 50.0,
        "last_5_win_rate": 50.0,
        "opponent_avg_win_rate_in_wins": 50.0,
        "first_round_finish_rate": 50.0,
        "ko_tko_win_rate": 50.0,
        "submission_win_rate": 50.0,
        "height_inches": 50.0,
        "reach_inches": 50.0,
        "age_years": 50.0,
        "sig_strikes_absorbed_per_fight": 50.0,
        "ko_tko_loss_rate": 50.0,
        "sub_loss_rate": 50.0,
        "decision_fight_win_rate": 50.0,
        "decision_rate": 50.0,
        "win_rate": 50.0,
        "ufc_fight_count": 50.0,
        "title_fight_wins": 50.0,
        "grappling_pace_decay_ratio": 1.0,
        "pace_decay_ratio": 1.0,
    }
    base.update(overrides)
    return base


def test_finisher_has_higher_pace_decay_than_fader() -> None:
    finisher = {
        "wins": 10,
        "losses": 2,
        "draws": 0,
        "career": {},
        "fight_history": [
            {"result": "win", "round": 1, "fight_time_seconds": 180, "sig_strikes_landed": 30},
            {"result": "win", "round": 1, "fight_time_seconds": 240, "sig_strikes_landed": 40},
            {"result": "win", "round": 5, "fight_time_seconds": 1485, "sig_strikes_landed": 200},
        ],
    }
    fader = {
        "wins": 10,
        "losses": 2,
        "draws": 0,
        "career": {},
        "fight_history": [
            {"result": "win", "round": 1, "fight_time_seconds": 300, "sig_strikes_landed": 50},
            {"result": "win", "round": 1, "fight_time_seconds": 300, "sig_strikes_landed": 45},
            {"result": "win", "round": 3, "fight_time_seconds": 900, "sig_strikes_landed": 45},
            {"result": "loss", "round": 3, "fight_time_seconds": 900, "sig_strikes_landed": 30},
        ],
    }

    finisher_stats, _ = compute_derived_stats(finisher, None)
    fader_stats, _ = compute_derived_stats(fader, None)

    assert finisher_stats["pace_decay_ratio"] is not None
    assert fader_stats["pace_decay_ratio"] is not None
    assert finisher_stats["pace_decay_ratio"] > fader_stats["pace_decay_ratio"]


def test_cardio_weight_scales_for_three_round_fights() -> None:
    from src.config import load_model_config, load_stats_config

    model_cfg = load_model_config()
    stats_cfg = load_stats_config()
    cardio_base = float(stats_cfg["categories"]["cardio"]["weight"])

    mult = _cardio_category_weight(model_cfg, scheduled_rounds=3, is_title_fight=False)
    assert mult == 0.75

    stats = {
        "finisher": _neutral_stats(pace_decay_ratio=0.9),
        "fader": _neutral_stats(pace_decay_ratio=0.5),
    }
    pred = predict_fight(
        "finisher",
        "fader",
        "Finisher",
        "Fader",
        stats,
        {"finisher": "Lightweight", "fader": "Lightweight"},
        scheduled_rounds=3,
    )
    cardio = next(c for c in pred.categories if c.name == "cardio")
    assert cardio.weight == cardio_base * 0.75
