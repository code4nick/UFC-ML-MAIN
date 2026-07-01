from __future__ import annotations

from datetime import date
from typing import Any

from src.scrapers.browser import fetch_html
from src.scrapers.derived_stats import build_research_context, compute_derived_stats
from src.scrapers.enrich import FightHistoryEnricher
from src.scrapers.parsers import (
    parse_event_page,
    parse_fighter_page,
    parse_upcoming_events,
)

UPCOMING_URL = "http://www.ufcstats.com/statistics/events/upcoming"
COMPLETED_URL = "http://www.ufcstats.com/statistics/events/completed"
EVENT_LIST_ROW_SELECTOR = "tr.b-statistics__table-row a[href*='event-details']"
FIGHTER_FIGHT_ROW_SELECTOR = "tr.b-fight-details__table-row"


class UFCStatsClient:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._page = None
        self._browser = None
        self._playwright = None

    def __enter__(self) -> "UFCStatsClient":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def get_html(self, url: str, *, wait_selector: str | None = None) -> str:
        if not self._page:
            raise RuntimeError("Client not started. Use 'with UFCStatsClient()'.")
        return fetch_html(self._page, url, wait_selector=wait_selector)

    def list_upcoming_events(self) -> list[dict[str, Any]]:
        return self._list_events(UPCOMING_URL)

    def list_completed_events(self) -> list[dict[str, Any]]:
        return self._list_events(COMPLETED_URL)

    def _list_events(self, url: str) -> list[dict[str, Any]]:
        html = self.get_html(url, wait_selector=EVENT_LIST_ROW_SELECTOR)
        events = parse_upcoming_events(html)
        if not events:
            raise ValueError(
                f"No events parsed from UFCStats ({url}). "
                "The page may not have finished loading — wait a moment and retry."
            )
        return events

    def get_event(self, event_url: str) -> dict[str, Any]:
        html = self.get_html(event_url)
        parsed = parse_event_page(html)
        parsed["url"] = event_url
        return parsed

    def get_fighter(self, fighter_url: str) -> dict[str, Any]:
        html = self.get_html(fighter_url, wait_selector=FIGHTER_FIGHT_ROW_SELECTOR)
        parsed = parse_fighter_page(html)
        parsed["url"] = fighter_url
        return parsed


def find_event(
    client: UFCStatsClient,
    *,
    event_name: str | None = None,
    event_url: str | None = None,
    upcoming_index: int = 0,
) -> dict[str, Any]:
    if event_url:
        event = client.get_event(event_url)
        event["ufcstats_id"] = event_url.rstrip("/").split("/")[-1]
        return event

    events = client.list_upcoming_events()
    if not events:
        raise ValueError("No upcoming events found on UFCStats.")

    if event_name:
        name_lower = event_name.lower()
        for item in events:
            if name_lower in item["name"].lower():
                return client.get_event(item["url"]) | {
                    "ufcstats_id": item["ufcstats_id"],
                    "event_date": item.get("event_date") or None,
                }
        raise ValueError(f"No upcoming event matching '{event_name}'.")

    if upcoming_index >= len(events):
        raise ValueError(f"upcoming_index {upcoming_index} out of range ({len(events)} events).")

    chosen = events[upcoming_index]
    event = client.get_event(chosen["url"])
    event["ufcstats_id"] = chosen["ufcstats_id"]
    if not event.get("event_date"):
        event["event_date"] = chosen.get("event_date")
    return event


def parse_reference_date(event_date: str | None) -> date | None:
    if not event_date:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            from datetime import datetime

            return datetime.strptime(event_date.strip(), fmt).date()
        except ValueError:
            continue
    return None


def ingest_event_data(client: UFCStatsClient, event: dict[str, Any]) -> dict[str, Any]:
    """Fetch all fighters for an event and return structured ingest payload."""
    ref_date = parse_reference_date(event.get("event_date"))
    fighter_cache: dict[str, dict[str, Any]] = {}
    payload_fights: list[dict[str, Any]] = []
    enricher = FightHistoryEnricher(client)

    for fight in event.get("fights", []):
        fight_entry: dict[str, Any] = {
            "fight": fight,
            "fighters": [],
        }
        for corner in ("fighter_red", "fighter_blue"):
            fmeta = fight[corner]
            fid = fmeta["ufcstats_id"]
            if fid not in fighter_cache:
                fighter = client.get_fighter(fmeta["url"])
                print(f"  Enriching {fighter['name']} ({len(fighter.get('fight_history', []))} UFC fights)...")
                fighter = enricher.enrich_fighter(fighter)
                stats, missing = compute_derived_stats(fighter, ref_date)
                context = build_research_context(
                    fighter,
                    fight,
                    ref_date,
                )
                fighter_cache[fid] = {
                    "profile": {
                        "ufcstats_id": fid,
                        "name": fighter["name"],
                        "nickname": fighter.get("nickname"),
                        "height_inches": fighter.get("height_inches"),
                        "weight_lbs": fighter.get("weight_lbs"),
                        "reach_inches": fighter.get("reach_inches"),
                        "stance": fighter.get("stance"),
                        "dob": fighter.get("dob"),
                    },
                    "stats": stats,
                    "missing_stats": missing,
                    "context": context,
                }
            fight_entry["fighters"].append(fighter_cache[fid])
        payload_fights.append(fight_entry)

    return {
        "event": event,
        "fights": payload_fights,
    }
