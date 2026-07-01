from __future__ import annotations

from typing import Any, Protocol

from src.scrapers.parsers import (
    extract_id_from_url,
    parse_event_date_only,
    parse_fight_detail_totals,
    parse_fighter_record,
)


class HtmlFetcher(Protocol):
    def get_html(self, url: str) -> str: ...


class FightHistoryEnricher:
    """Deep-scrape fight details, event dates, and opponent records."""

    def __init__(self, client: HtmlFetcher):
        self.client = client
        self._fight_cache: dict[str, dict[str, Any]] = {}
        self._event_date_cache: dict[str, str | None] = {}
        self._opponent_cache: dict[str, dict[str, Any]] = {}

    def enrich_fighter(self, fighter: dict[str, Any]) -> dict[str, Any]:
        fighter_id = extract_id_from_url(fighter.get("url", ""))
        if not fighter_id:
            return fighter

        enriched_history: list[dict[str, Any]] = []
        for fight in fighter.get("fight_history", []):
            entry = dict(fight)
            fight_url = entry.get("fight_url")
            if fight_url:
                detail = self._get_fight_detail(fight_url, fighter_id)
                if detail.get("sig_strikes_landed") is not None:
                    entry["sig_strikes_landed"] = detail["sig_strikes_landed"]
                entry["sig_strikes_absorbed"] = detail.get("sig_strikes_absorbed")
                entry["reversals"] = detail.get("reversals")
                entry["ctrl_time_seconds"] = detail.get("ctrl_time_seconds")
                if detail.get("is_title_fight"):
                    entry["is_title_fight"] = True
                if detail.get("event_name") and not entry.get("event"):
                    entry["event"] = detail["event_name"]
                event_url = detail.get("event_url")
                if event_url:
                    entry["event_date"] = self._get_event_date(event_url)

            opponent_url = entry.get("opponent_url")
            if opponent_url:
                record = self._get_opponent_record(opponent_url)
                entry["opponent_win_rate"] = record.get("win_rate")

            enriched_history.append(entry)

        fighter = dict(fighter)
        fighter["fight_history"] = enriched_history
        return fighter

    def _get_fight_detail(self, fight_url: str, fighter_id: str) -> dict[str, Any]:
        if fight_url not in self._fight_cache:
            html = self.client.get_html(fight_url)
            self._fight_cache[fight_url] = parse_fight_detail_totals(html)
        totals = self._fight_cache[fight_url]
        fighter_stats = totals.get("fighters", {}).get(fighter_id, {})
        return {
            "event_url": totals.get("event_url"),
            "event_name": totals.get("event_name"),
            "sig_strikes_landed": fighter_stats.get("sig_strikes_landed"),
            "sig_strikes_absorbed": fighter_stats.get("sig_strikes_absorbed"),
            "reversals": fighter_stats.get("reversals"),
            "ctrl_time_seconds": fighter_stats.get("ctrl_time_seconds"),
            "is_title_fight": totals.get("is_title_fight", False),
        }

    def _get_event_date(self, event_url: str) -> str | None:
        if event_url not in self._event_date_cache:
            html = self.client.get_html(event_url)
            self._event_date_cache[event_url] = parse_event_date_only(html)
        return self._event_date_cache[event_url]

    def _get_opponent_record(self, opponent_url: str) -> dict[str, Any]:
        opponent_id = extract_id_from_url(opponent_url)
        if opponent_id not in self._opponent_cache:
            html = self.client.get_html(opponent_url)
            self._opponent_cache[opponent_id] = parse_fighter_record(html)
        return self._opponent_cache[opponent_id]
