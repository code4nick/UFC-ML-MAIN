from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_DB_PATH
from src.engine.betting import analyze_bet, format_american
from src.services.card_loader import (
    get_fight_market_lines,
    load_card_predictions,
    load_merged_odds,
)


def _format_pct(prob: float) -> str:
    return f"{prob * 100:.1f}%"


def _print_analysis(analysis, yaml_odds: dict) -> None:
    blended = analysis.blended
    pred = blended.math
    wc = analysis.weight_class or "Unknown"
    print()
    print("=" * 72)
    print(f"{analysis.red_name}  vs  {analysis.blue_name}")
    print(f"  {wc}")
    print("-" * 72)

    red_ml, blue_ml, _, _, source = get_fight_market_lines(analysis, yaml_odds)
    bet = analyze_bet(
        blended.pick_corner,
        blended.pick_name,
        blended.win_prob,
        blended.tier,
        red_ml,
        blue_ml,
        market_implied=(
            analysis.polymarket.red_prob
            if blended.pick_corner == "red" and analysis.polymarket
            else analysis.polymarket.blue_prob
            if analysis.polymarket
            else None
        ),
        market_source=source,
    )
    ml_str = format_american(bet.pick_ml) if bet.pick_ml is not None else "—"
    print(f"  PICK: {blended.pick_name}  |  {blended.tier}  |  {_format_pct(blended.win_prob)}  |  ML {ml_str}")
    print(f"  Math: {_format_pct(blended.math_win_prob)}  ->  Final (research): {_format_pct(blended.win_prob)}")
    print(f"  Range: {_format_pct(blended.prob_low)} - {_format_pct(blended.prob_high)}")
    print(f"  Red: {_format_pct(blended.red_win_prob)}  |  Blue: {_format_pct(blended.blue_win_prob)}")

    if analysis.polymarket:
        p = analysis.polymarket
        print(f"  Polymarket: {_format_pct(p.red_prob)} / {_format_pct(p.blue_prob)}")

    if bet.vegas_implied is not None:
        print(
            f"  BET: {bet.verdict}  |  {bet.market_source} {_format_pct(bet.vegas_implied)}  |  "
            f"Edge {bet.edge_points:+.1f} pts  |  EV ${bet.ev_per_unit:+.2f}/$1"
        )
        print(f"  {bet.detail}")

    if blended.research.why_pick:
        print("  Why this pick:")
        for b in blended.research.why_pick[:4]:
            print(f"    + {b}")
    if blended.research.watch_out:
        print("  Watch out:")
        for b in blended.research.watch_out[:4]:
            print(f"    - {b}")

    print()
    print("  Category breakdown (0-100 percentile scores):")
    print(f"  {'Category':<16} {'Red':>6} {'Blue':>6} {'Gap':>7}")
    for cat in pred.categories:
        label = cat.name.replace("_", " ").title()
        print(f"  {label:<16} {cat.red_score:6.1f} {cat.blue_score:6.1f} {cat.gap:+7.1f}")


def run_predictions(
    *,
    db_path: Path | None = None,
    event_name: str | None = None,
    fight_query: str | None = None,
    odds_file: Path | None = None,
) -> None:
    card = load_card_predictions(db_path, event_name=event_name, use_polymarket=True)
    yaml_odds = load_merged_odds(odds_file)

    print(f"Event: {card.event['name']} ({card.event.get('event_date') or 'date TBD'})")
    poly = sum(1 for a in card.analyses if a.polymarket)
    print(f"Polymarket lines: {poly}/{len(card.analyses)}")

    for analysis in card.analyses:
        label = f"{analysis.red_name} vs {analysis.blue_name}"
        if fight_query and fight_query.lower() not in label.lower():
            continue
        _print_analysis(analysis, yaml_odds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UFC AI — predictions + Polymarket + research")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--event-name", type=str)
    parser.add_argument("--fight", type=str)
    parser.add_argument("--odds-file", type=Path, help="Optional YAML fallback odds")
    args = parser.parse_args(argv)

    try:
        run_predictions(
            db_path=args.db,
            event_name=args.event_name,
            fight_query=args.fight,
            odds_file=args.odds_file,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
