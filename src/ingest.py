from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_ROSTER_CARDS,
    MAX_ROSTER_CARDS,
    MIN_DIVISION_POOL,
    ROSTER_CARD_STEP,
)
from src.db.connection import get_connection, init_db
from src.db.repository import Repository, utc_now_iso
from src.scrapers.ufcstats import UFCStatsClient, find_event, ingest_event_data


def _print_summary(repo: Repository) -> None:
    summary = repo.summary()
    print("\nDatabase summary")
    print("-" * 40)
    for table, count in summary["counts"].items():
        print(f"  {table}: {count}")
    if summary["latest_event"]:
        ev = summary["latest_event"]
        print(f"\nLatest event: {ev['name']} ({ev.get('event_date') or 'date TBD'})")
        print(f"  scraped_at: {ev['scraped_at']}")


def _fighter_id_map(repo: Repository, payload: dict, scraped_at: str) -> dict[str, int]:
    ids: dict[str, int] = {}
    for fight_block in payload["fights"]:
        for fighter in fight_block["fighters"]:
            profile = fighter["profile"]
            ids[profile["ufcstats_id"]] = repo.upsert_fighter(profile, scraped_at)
    return ids


def _persist_event_payload(
    repo: Repository,
    event: dict,
    payload: dict,
    scraped_at: str,
) -> None:
    event_id = repo.upsert_event(
        ufcstats_id=event["ufcstats_id"],
        name=event["name"],
        event_date=event.get("event_date"),
        location=event.get("location"),
        scraped_at=scraped_at,
    )
    fighter_ids = _fighter_id_map(repo, payload, scraped_at)

    for fight_block in payload["fights"]:
        fight = fight_block["fight"]
        red_id = fighter_ids[fight["fighter_red"]["ufcstats_id"]]
        blue_id = fighter_ids[fight["fighter_blue"]["ufcstats_id"]]
        fight_id = repo.upsert_fight(
            {
                "ufcstats_id": fight["ufcstats_id"],
                "event_id": event_id,
                "fighter_red_id": red_id,
                "fighter_blue_id": blue_id,
                "weight_class": fight.get("weight_class"),
                "is_title_fight": fight.get("is_title_fight", False),
                "scheduled_rounds": fight.get("scheduled_rounds", 3),
            },
            scraped_at,
        )

        for fighter in fight_block["fighters"]:
            fid = fighter_ids[fighter["profile"]["ufcstats_id"]]
            repo.save_stat_snapshot(
                fighter_id=fid,
                event_id=event_id,
                stats=fighter["stats"],
                missing=fighter["missing_stats"],
                scraped_at=scraped_at,
            )
            repo.save_context_snapshot(
                fighter_id=fid,
                fight_id=fight_id,
                context=fighter["context"],
                scraped_at=scraped_at,
            )


def _ingest_event_with_client(
    client: UFCStatsClient,
    repo: Repository,
    event_meta: dict,
    scraped_at: str,
    *,
    label: str | None = None,
) -> None:
    event = client.get_event(event_meta["url"])
    event["ufcstats_id"] = event_meta["ufcstats_id"]
    if not event.get("event_date"):
        event["event_date"] = event_meta.get("event_date")

    prefix = f"{label} " if label else ""
    print(
        f"{prefix}Fetching card: {event['name']} "
        f"({event.get('event_date') or 'date TBD'}) — {len(event.get('fights', []))} fights"
    )
    payload = ingest_event_data(client, event)
    _persist_event_payload(repo, event, payload, scraped_at)


def _ingest_card_batch(
    client: UFCStatsClient,
    repo: Repository,
    batch: list[dict],
    scraped_at: str,
    *,
    label_prefix: str = "",
    skip_existing: bool = True,
) -> int:
    """Ingest each card in batch; commit after every card so crashes keep progress."""
    ingested = 0
    for index, item in enumerate(batch, start=1):
        if skip_existing and repo.has_event(item["ufcstats_id"]):
            print(f"{label_prefix}[{index}/{len(batch)}] Skipping (already in DB): {item['name']}")
            continue
        label = f"{label_prefix}[{index}/{len(batch)}]".strip()
        _ingest_event_with_client(
            client,
            repo,
            item,
            scraped_at,
            label=label,
        )
        repo.conn.commit()
        ingested += 1
        print(f"  Saved to database ({index}/{len(batch)}).")
    return ingested


def _ingest_roster_until_divisions_full(
    client: UFCStatsClient,
    repo: Repository,
    completed: list[dict],
    scraped_at: str,
    *,
    start_cards: int,
    skip_existing: bool = True,
) -> tuple[int, int, dict[str, int]]:
    """Ingest completed cards, expanding the window until each division meets its pool minimum."""
    target = min(max(start_cards, 1), len(completed))
    total_ingested = 0
    processed = 0
    thin: dict[str, int] = {}

    while True:
        if target > processed:
            batch = completed[processed:target]
            ingested = _ingest_card_batch(
                client,
                repo,
                batch,
                scraped_at,
                skip_existing=skip_existing,
            )
            total_ingested += ingested
            processed = target
            repo.conn.commit()

        thin = repo.thin_divisions(target)
        if not thin:
            return total_ingested, target, {}

        cap = min(MAX_ROSTER_CARDS, len(completed))
        if target >= cap:
            return total_ingested, target, thin

        next_target = min(target + ROSTER_CARD_STEP, cap)
        if next_target <= target:
            return total_ingested, target, thin
        print(
            f"  Thin division pool(s) after {target} card(s): "
            + ", ".join(f"{wc} ({n})" for wc, n in sorted(thin.items()))
            + f" — expanding to {next_target} cards..."
        )
        target = next_target


def run_ingest_last_cards(
    *,
    count: int = DEFAULT_ROSTER_CARDS,
    db_path: Path | None = None,
    headless: bool = True,
    refresh: bool = False,
) -> None:
    """Ingest the N most recent completed UFC cards for division pool depth."""
    if count < 1:
        raise ValueError("count must be at least 1.")

    init_db(db_path)
    scraped_at = utc_now_iso()

    with UFCStatsClient(headless=headless) as client:
        completed = client.list_completed_events()
        if not completed:
            raise ValueError(
                "No completed events found on UFCStats. "
                "Check your network connection and retry in a minute."
            )

        batch = completed[:count]
        if refresh:
            print("Refresh mode: re-scraping cards even if already in database.")
        print(
            f"Ingesting up to {len(batch)} completed card(s) for roster depth "
            f"(expands until each division hits its pool minimum — {MIN_DIVISION_POOL} men's, "
            f"8 women's, 6 catchweight)..."
        )

        with get_connection(db_path) as conn:
            repo = Repository(conn)
            ingested, cards_used, thin = _ingest_roster_until_divisions_full(
                client,
                repo,
                completed,
                scraped_at,
                start_cards=count,
                skip_existing=not refresh,
            )
            _print_summary(repo)

    if thin:
        print(
            "\nWarning: some divisions still below their pool minimum after "
            f"{cards_used} card(s): "
            + ", ".join(f"{wc} ({n})" for wc, n in sorted(thin.items()))
        )
    else:
        print(f"\nAll divisions meet pool minimums ({cards_used} card window).")

    print(f"\nRoster ingest complete ({ingested} new card(s), {cards_used} card window).")


def run_ingest(
    *,
    event_name: str | None = None,
    event_url: str | None = None,
    upcoming: bool = False,
    upcoming_index: int = 0,
    db_path: Path | None = None,
    headless: bool = True,
    export_json: Path | None = None,
    roster_cards: int = 0,
    refresh: bool = False,
) -> None:
    init_db(db_path)
    scraped_at = utc_now_iso()

    with UFCStatsClient(headless=headless) as client:
        if roster_cards > 0:
            completed = client.list_completed_events()
            if completed:
                print(
                    f"Ingesting completed cards for roster depth "
                    f"(target {MIN_DIVISION_POOL}+ fighters per division)..."
                )
                if refresh:
                    print("Refresh mode: re-scraping roster cards even if already in database.")
                with get_connection(db_path) as conn:
                    repo = Repository(conn)
                    _, cards_used, thin = _ingest_roster_until_divisions_full(
                        client,
                        repo,
                        completed,
                        scraped_at,
                        start_cards=roster_cards,
                        skip_existing=not refresh,
                    )
                    if thin:
                        print(
                            "Warning: thin divisions after roster ingest: "
                            + ", ".join(f"{wc} ({n})" for wc, n in sorted(thin.items()))
                        )
                    else:
                        print(
                            f"Roster depth OK ({cards_used} card window, "
                            f"{MIN_DIVISION_POOL}+ per division)."
                        )
            else:
                print("Warning: no completed events found; skipping roster ingest.")

        if upcoming:
            event_meta = client.list_upcoming_events()
            if not event_meta:
                raise ValueError("No upcoming events found on UFCStats.")
            if upcoming_index >= len(event_meta):
                raise ValueError(
                    f"upcoming_index {upcoming_index} out of range ({len(event_meta)} events)."
                )
            chosen = event_meta[upcoming_index]
            with get_connection(db_path) as conn:
                repo = Repository(conn)
                _ingest_event_with_client(client, repo, chosen, scraped_at)
                conn.commit()
                _print_summary(repo)
        else:
            event = find_event(client, event_name=event_name, event_url=event_url)
            print(f"Fetching card: {event['name']} ({event.get('event_date') or 'date TBD'})")
            print(f"  Fights on card: {len(event.get('fights', []))}")
            payload = ingest_event_data(client, event)

            if export_json:
                export_json.parent.mkdir(parents=True, exist_ok=True)
                export_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(f"Exported raw payload to {export_json}")

            with get_connection(db_path) as conn:
                repo = Repository(conn)
                _persist_event_payload(repo, event, payload, scraped_at)
                conn.commit()
                _print_summary(repo)

    print("\nStep 1 ingest complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UFC AI — Step 1 data ingest")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument(
        "--last-cards",
        nargs="?",
        const=DEFAULT_ROSTER_CARDS,
        type=int,
        metavar="N",
        help=f"Ingest last N completed cards only (default {DEFAULT_ROSTER_CARDS})",
    )
    parser.add_argument(
        "--with-roster",
        action="store_true",
        help=(
            f"With --upcoming, also re-ingest last {DEFAULT_ROSTER_CARDS} completed cards "
            "(slow; use for monthly refresh)"
        ),
    )
    parser.add_argument("--upcoming", action="store_true", help="Ingest next upcoming UFC card")
    parser.add_argument("--upcoming-index", type=int, default=0, help="0=nearest upcoming event")
    parser.add_argument("--event-name", type=str, help="Partial event name match")
    parser.add_argument("--event-url", type=str, help="Full UFCStats event URL")
    parser.add_argument("--status", action="store_true", help="Show database summary only")
    parser.add_argument("--headed", action="store_true", help="Show browser window while scraping")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-scrape cards even if already in DB (updates fighter stats after code changes)",
    )
    parser.add_argument("--export-json", type=Path, help="Optional raw JSON export path")
    args = parser.parse_args(argv)

    if args.status:
        init_db(args.db)
        with get_connection(args.db) as conn:
            _print_summary(Repository(conn))
        return 0

    event_mode = args.upcoming or args.event_name or args.event_url or args.last_cards is not None

    if args.last_cards is not None and not args.upcoming and not args.event_name and not args.event_url:
        run_ingest_last_cards(
            count=args.last_cards,
            db_path=args.db,
            headless=not args.headed,
            refresh=args.refresh,
        )
        return 0

    if not event_mode:
        parser.error(
            "Specify --upcoming, --last-cards, --event-name, --event-url, or --status."
        )

    roster_cards = 0
    if args.upcoming and args.with_roster:
        roster_cards = args.last_cards if args.last_cards is not None else DEFAULT_ROSTER_CARDS

    run_ingest(
        event_name=args.event_name,
        event_url=args.event_url,
        upcoming=args.upcoming,
        upcoming_index=args.upcoming_index,
        db_path=args.db,
        headless=not args.headed,
        export_json=args.export_json,
        roster_cards=roster_cards,
        refresh=args.refresh,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
