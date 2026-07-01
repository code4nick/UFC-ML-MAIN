"""Unit tests for decision_fight_win_rate (Fight IQ)."""

from __future__ import annotations

from src.scrapers.derived_stats import compute_derived_stats


def _fighter(history: list[dict]) -> dict:
    return {"wins": 0, "losses": 0, "draws": 0, "career": {}, "fight_history": history}


def test_finisher_with_no_decisions_has_no_rate() -> None:
    stats, missing = compute_derived_stats(
        _fighter(
            [
                {"result": "win", "method": "KO/TKO", "round": 1},
                {"result": "win", "method": "Submission", "round": 2},
            ]
        ),
        None,
    )
    assert stats["decision_fight_win_rate"] is None
    assert stats["decision_win_rate"] == 0.0
    assert "decision_fight_win_rate" in missing


def test_decision_record_uses_wins_over_all_decision_fights() -> None:
    fighter = _fighter(
        [
            {"result": "win", "method": "Decision - Unanimous", "round": 3},
            {"result": "win", "method": "Decision - Split", "round": 3},
            {"result": "win", "method": "Decision - Unanimous", "round": 3},
            {"result": "loss", "method": "Decision - Unanimous", "round": 3},
            {"result": "win", "method": "KO/TKO", "round": 1},
        ]
    )
    fighter["wins"] = 4
    fighter["losses"] = 1
    stats, missing = compute_derived_stats(fighter, None)
    assert stats["decision_fight_win_rate"] == 0.75
    assert stats["decision_win_rate"] == 0.75
    assert "decision_fight_win_rate" not in missing
