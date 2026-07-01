from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_DB_PATH
from src.services.ledger import (
    get_graded_predictions,
    get_lifetime_record,
    grade_pending,
    log_card_picks,
)


def _print_record() -> None:
    record = get_lifetime_record()
    print("\nAI Lifetime · Moneyline")
    print("-" * 40)
    print(f"  Wins:     {record.wins}")
    print(f"  Losses:   {record.losses}")
    print(f"  Pending:  {record.pending}")
    if record.hit_rate is not None:
        print(f"  Hit Rate: {record.hit_rate * 100:.1f}%")
    print(f"  Units:    {record.units:+.2f}u")

    graded = get_graded_predictions(limit=20)
    if graded:
        print("\nRecent results:")
        for row in graded:
            mark = "W" if row["status"] == "win" else "L"
            fight = f"{row['red_name']} vs {row['blue_name']}"
            units = row.get("units") or 0
            print(
                f"  [{mark}] {row['pick_name']} ({row['tier']}) — {fight} "
                f"| {units:+.2f}u | {row.get('event_name', '')}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UFC AI — prediction ledger (Step 7)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--log", action="store_true", help="Lock current card picks to ledger")
    parser.add_argument("--grade", action="store_true", help="Grade pending picks from fight results")
    parser.add_argument("--record", action="store_true", help="Show lifetime record")
    parser.add_argument("--event-name", type=str, help="Filter by event name")
    args = parser.parse_args(argv)

    if not (args.log or args.grade or args.record):
        parser.error("Specify --log, --grade, and/or --record.")

    try:
        if args.log:
            result = log_card_picks(args.db, event_name=args.event_name)
            print(f"Locked picks for {result.event_name}: {result.logged} logged, {result.skipped} skipped.")
        if args.grade:
            n = grade_pending(args.db, event_name=args.event_name)
            print(f"Graded {n} prediction(s).")
        if args.record:
            _print_record()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
