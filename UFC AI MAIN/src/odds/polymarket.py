from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

GAMMA_API = "https://gamma-api.polymarket.com"
USER_AGENT = "UFC-AI-Predictor/1.0"


@dataclass
class PolymarketLine:
    event_title: str
    red_name: str
    blue_name: str
    red_prob: float
    blue_prob: float
    red_price: float
    blue_price: float
    market_slug: str | None = None

    @property
    def red_ml(self) -> int:
        return prob_to_american(self.red_prob)

    @property
    def blue_ml(self) -> int:
        return prob_to_american(self.blue_prob)


def prob_to_american(prob: float) -> int:
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return -round((prob / (1.0 - prob)) * 100)
    return round(((1.0 - prob) / prob) * 100)


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = text.replace("'", "").replace(".", "")
    text = re.sub(r"\s+", " ", text)
    return text


def _names_match(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    return na == nb or na in nb or nb in na


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    query = urllib.parse.urlencode(params or {})
    url = f"{GAMMA_API}{path}"
    if query:
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _parse_prices(raw: Any) -> list[float]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return [float(x) for x in raw]


def _parse_outcomes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return [str(x) for x in raw]


def _moneyline_market(event: dict[str, Any]) -> dict[str, Any] | None:
    title = event.get("title") or ""
    for market in event.get("markets") or []:
        outcomes = _parse_outcomes(market.get("outcomes"))
        if len(outcomes) != 2:
            continue
        if outcomes[0] in {"Yes", "No", "Over", "Under"}:
            continue
        question = market.get("question") or ""
        if question == title or " vs " in question or " vs. " in question:
            prices = _parse_prices(market.get("outcomePrices"))
            if len(prices) == 2:
                return {
                    "outcomes": outcomes,
                    "prices": prices,
                    "slug": market.get("slug"),
                }
    return None


def search_event_markets(query: str, limit: int = 50) -> list[dict[str, Any]]:
    data = _api_get(
        "/public-search",
        {"q": query, "limit_per_type": limit, "events_status": "active"},
    )
    return data.get("events") or []


def fetch_card_lines(event_query: str) -> list[PolymarketLine]:
    """Fetch moneyline markets for a UFC card from Polymarket."""
    events = search_event_markets(event_query)
    lines: list[PolymarketLine] = []
    seen: set[str] = set()

    for event in events:
        title = event.get("title") or ""
        if "ufc" not in title.lower():
            continue
        ml = _moneyline_market(event)
        if not ml:
            continue
        key = normalize_name(title)
        if key in seen:
            continue
        seen.add(key)

        outcomes = ml["outcomes"]
        prices = ml["prices"]
        lines.append(
            PolymarketLine(
                event_title=title,
                red_name=outcomes[0],
                blue_name=outcomes[1],
                red_prob=prices[0],
                blue_prob=prices[1],
                red_price=prices[0],
                blue_price=prices[1],
                market_slug=ml.get("slug"),
            )
        )
    return lines


def match_line_to_fight(
    red_name: str,
    blue_name: str,
    lines: list[PolymarketLine],
) -> PolymarketLine | None:
    for line in lines:
        a, b = line.red_name, line.blue_name
        if _names_match(red_name, a) and _names_match(blue_name, b):
            return line
        if _names_match(red_name, b) and _names_match(blue_name, a):
            return PolymarketLine(
                event_title=line.event_title,
                red_name=red_name,
                blue_name=blue_name,
                red_prob=line.blue_prob,
                blue_prob=line.red_prob,
                red_price=line.blue_price,
                blue_price=line.red_price,
                market_slug=line.market_slug,
            )
    return None
