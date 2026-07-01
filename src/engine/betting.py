from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import CONFIG_DIR, load_yaml
from src.odds.polymarket import prob_to_american


def load_betting_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "betting.yaml")


@dataclass
class BetAnalysis:
    pick_name: str
    pick_corner: str
    pick_ml: int | None
    model_prob: float
    vegas_implied: float | None
    market_source: str | None
    edge: float | None
    edge_points: float | None
    ev_per_unit: float | None
    half_kelly_fraction: float | None
    half_kelly_stake: float | None
    verdict: str
    detail: str


def american_to_decimal(odds: int) -> float:
    if odds == 0:
        raise ValueError("American odds cannot be 0")
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def american_to_implied_prob(odds: int) -> float:
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def format_american(odds: int) -> str:
    return f"+{odds}" if odds > 0 else str(odds)


def kelly_fraction(prob: float, decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - prob
    return (b * prob - q) / b


def analyze_bet(
    pred_pick_corner: str,
    pred_pick_name: str,
    model_prob: float,
    tier: str,
    red_ml: int | None,
    blue_ml: int | None,
    *,
    bankroll: float | None = None,
    betting_cfg: dict[str, Any] | None = None,
    market_implied: float | None = None,
    market_source: str = "Polymarket",
) -> BetAnalysis:
    cfg = betting_cfg or load_betting_config()
    bankroll = bankroll if bankroll is not None else float(cfg.get("default_bankroll", 1000))
    min_edge = float(cfg.get("min_edge", 0.03))
    max_kelly = float(cfg.get("max_kelly_fraction", 0.25))
    use_half = bool(cfg.get("half_kelly", True))
    bettable = set(cfg.get("bettable_tiers", ["LOCK", "STRONG", "LEAN"]))

    pick_ml = red_ml if pred_pick_corner == "red" else blue_ml
    if pick_ml is None and market_implied is None:
        return BetAnalysis(
            pick_name=pred_pick_name,
            pick_corner=pred_pick_corner,
            pick_ml=None,
            model_prob=model_prob,
            vegas_implied=None,
            market_source=None,
            edge=None,
            edge_points=None,
            ev_per_unit=None,
            half_kelly_fraction=None,
            half_kelly_stake=None,
            verdict="NO_LINE",
            detail="No Polymarket or sportsbook line available.",
        )

    if market_implied is not None:
        vegas_implied = market_implied
    else:
        vegas_implied = american_to_implied_prob(int(pick_ml))

    if pick_ml is None and market_implied is not None:
        pick_ml = prob_to_american(market_implied)

    edge = model_prob - vegas_implied
    edge_points = edge * 100.0
    decimal_odds = american_to_decimal(pick_ml) if pick_ml is not None else (1.0 / market_implied if market_implied else 1.0)
    ev_per_unit = model_prob * (decimal_odds - 1.0) - (1.0 - model_prob)

    raw_kelly = max(0.0, kelly_fraction(model_prob, decimal_odds))
    if use_half:
        raw_kelly *= 0.5
    kelly_frac = min(raw_kelly, max_kelly)
    kelly_stake = round(kelly_frac * bankroll, 2)

    if tier not in bettable and edge < min_edge * 2:
        return BetAnalysis(
            pick_name=pred_pick_name,
            pick_corner=pred_pick_corner,
            pick_ml=pick_ml,
            model_prob=model_prob,
            vegas_implied=vegas_implied,
            market_source=market_source,
            edge=edge,
            edge_points=edge_points,
            ev_per_unit=ev_per_unit,
            half_kelly_fraction=kelly_frac,
            half_kelly_stake=kelly_stake,
            verdict="PASS",
            detail=f"Low confidence ({tier}) and insufficient edge ({edge_points:+.1f} pts).",
        )

    if edge < min_edge:
        return BetAnalysis(
            pick_name=pred_pick_name,
            pick_corner=pred_pick_corner,
            pick_ml=pick_ml,
            model_prob=model_prob,
            vegas_implied=vegas_implied,
            market_source=market_source,
            edge=edge,
            edge_points=edge_points,
            ev_per_unit=ev_per_unit,
            half_kelly_fraction=kelly_frac,
            half_kelly_stake=kelly_stake,
            verdict="PASS",
            detail=f"No edge — model {model_prob:.1%} vs {market_source} {vegas_implied:.1%} ({edge_points:+.1f} pts).",
        )

    is_dog = (pick_ml or 0) > 0
    ml_label = format_american(pick_ml) if pick_ml is not None else f"{vegas_implied:.1%} implied"
    if is_dog:
        verdict = "VALUE_DOG"
        detail = f"Value underdog — model sides with {pred_pick_name} at {ml_label} ({market_source})."
    else:
        verdict = "VALUE_FAV"
        detail = f"Edge on the favorite — {pred_pick_name} {ml_label} ({market_source})."

    return BetAnalysis(
        pick_name=pred_pick_name,
        pick_corner=pred_pick_corner,
        pick_ml=pick_ml,
        model_prob=model_prob,
        vegas_implied=vegas_implied,
        market_source=market_source,
        edge=edge,
        edge_points=edge_points,
        ev_per_unit=ev_per_unit,
        half_kelly_fraction=kelly_frac,
        half_kelly_stake=kelly_stake,
        verdict=verdict,
        detail=detail,
    )
