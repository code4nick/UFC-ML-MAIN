"""Unit tests for bout-line and win-rate shrinkage parsing."""

from __future__ import annotations

from src.scrapers.derived_stats import compute_derived_stats
from src.scrapers.parsers import parse_bout_line, parse_fight_detail_meta
from bs4 import BeautifulSoup


def test_parse_bout_line_title_fight() -> None:
    wc, is_title, rounds = parse_bout_line("UFC Lightweight Title Bout")
    assert wc == "UFC Lightweight Title Bout"
    assert is_title is True
    assert rounds == 5


def test_parse_bout_line_non_title() -> None:
    wc, is_title, rounds = parse_bout_line("Welterweight Bout")
    assert is_title is False
    assert rounds == 3


def test_parse_fight_detail_meta_from_html() -> None:
    html = """
    <html><body>
      <table><tr>
        <td class="b-fight-details__table-col">Lightweight Title Bout</td>
      </tr></table>
    </body></html>
    """
    meta = parse_fight_detail_meta(BeautifulSoup(html, "lxml"))
    assert meta["is_title_fight"] is True
    assert meta["scheduled_rounds"] == 5


def test_win_rate_shrinks_for_low_ufc_fight_count() -> None:
    fighter = {
        "wins": 3,
        "losses": 0,
        "draws": 0,
        "career": {},
        "fight_history": [
            {"result": "win", "method": "KO/TKO", "round": 1},
            {"result": "win", "method": "KO/TKO", "round": 1},
            {"result": "win", "method": "KO/TKO", "round": 1},
        ],
    }
    stats, _ = compute_derived_stats(fighter, None)
    assert stats["win_rate"] is not None
    assert stats["win_rate"] < 1.0
    assert stats["win_rate"] == (1.0 * 3 + 0.5 * 4) / 7


def test_title_fight_wins_uses_per_fight_flag() -> None:
    fighter = {
        "wins": 2,
        "losses": 0,
        "draws": 0,
        "career": {},
        "fight_history": [
            {
                "result": "win",
                "method": "Decision - Unanimous",
                "round": 5,
                "is_title_fight": True,
                "event": "UFC 300",
            },
            {
                "result": "win",
                "method": "KO/TKO",
                "round": 1,
                "event": "UFC Fight Night",
            },
        ],
    }
    stats, _ = compute_derived_stats(fighter, None)
    assert stats["title_fight_wins"] == 1.0
