from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from src.config import load_model_config, load_stats_config


@dataclass
class CategoryBreakdown:
    name: str
    red_score: float
    blue_score: float
    gap: float
    weight: float


@dataclass
class FightPrediction:
    fight_id: int
    weight_class: str | None
    red_name: str
    blue_name: str
    pick_name: str
    pick_corner: str
    red_win_prob: float
    blue_win_prob: float
    win_prob: float
    prob_low: float
    prob_high: float
    tier: str
    total_edge: float
    categories: list[CategoryBreakdown] = field(default_factory=list)


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _percentile_rank(value: float, pool: list[float]) -> float:
    if not pool:
        return 50.0
    below = sum(1 for v in pool if v < value)
    equal = sum(1 for v in pool if v == value)
    return 100.0 * (below + 0.5 * equal) / len(pool)


def _stat_direction(stat_key: str, definitions: dict[str, Any]) -> int:
    meta = definitions.get(stat_key, {})
    hib = meta.get("higher_is_better")
    if hib is False:
        return -1
    return 1


def impute_missing(
    fighter_stats: dict[str, dict[str, Any]],
    missing_keys: dict[str, list[str]],
    weight_classes: dict[str, str | None],
) -> dict[str, dict[str, Any]]:
    """Fill null stats with weight-class median, then card-wide median."""
    stat_keys = list(next(iter(fighter_stats.values())).keys()) if fighter_stats else []
    filled = {fid: dict(stats) for fid, stats in fighter_stats.items()}

    for key in stat_keys:
        by_class: dict[str | None, list[float]] = {}
        card_values: list[float] = []
        for fid, stats in fighter_stats.items():
            val = stats.get(key)
            if val is not None:
                wc = weight_classes.get(fid)
                by_class.setdefault(wc, []).append(float(val))
                card_values.append(float(val))

        card_median = sorted(card_values)[len(card_values) // 2] if card_values else None

        for fid, stats in fighter_stats.items():
            if stats.get(key) is not None:
                continue
            wc = weight_classes.get(fid)
            class_pool = by_class.get(wc, [])
            if class_pool:
                filled[fid][key] = sorted(class_pool)[len(class_pool) // 2]
            elif card_median is not None:
                filled[fid][key] = card_median

    return filled


def normalize_fighter_stats(
    fighter_stats: dict[str, dict[str, Any]],
    weight_classes: dict[str, str | None],
    definitions: dict[str, Any],
    *,
    pool_by_weight_class: bool = False,
) -> dict[str, dict[str, float]]:
    """Percentile ranks per stat within the event pool (or weight class)."""
    stat_keys = list(next(iter(fighter_stats.values())).keys()) if fighter_stats else []
    normalized: dict[str, dict[str, float]] = {fid: {} for fid in fighter_stats}

    for key in stat_keys:
        direction = _stat_direction(key, definitions)
        by_class: dict[str | None, list[tuple[str, float]]] = {}
        card_items: list[tuple[str, float]] = []

        for fid, stats in fighter_stats.items():
            val = stats.get(key)
            if val is None:
                continue
            wc = weight_classes.get(fid)
            card_items.append((fid, float(val)))
            by_class.setdefault(wc, []).append((fid, float(val)))

        def assign_pool(items: list[tuple[str, float]]) -> None:
            pool = [v for _, v in items]
            for fid, val in items:
                pct = _percentile_rank(val, pool)
                if direction < 0:
                    pct = 100.0 - pct
                normalized[fid][key] = pct

        if pool_by_weight_class:
            for items in by_class.values():
                assign_pool(items)
        else:
            assign_pool(card_items)

        for fid in fighter_stats:
            if key not in normalized[fid]:
                normalized[fid][key] = 50.0

    return normalized


def category_scores(
    normalized: dict[str, dict[str, float]],
    categories_cfg: dict[str, Any],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for fid, stats in normalized.items():
        scores[fid] = {}
        for cat_name, cat in categories_cfg.items():
            keys = cat["stats"]
            values = [stats[k] for k in keys if k in stats]
            scores[fid][cat_name] = sum(values) / len(values) if values else 50.0
    return scores


def assign_tier(prob: float, tiers: dict[str, float]) -> str:
    if prob >= tiers["lock_min"]:
        return "LOCK"
    if prob >= tiers["strong_min"]:
        return "STRONG"
    if prob >= tiers["lean_min"]:
        return "LEAN"
    if prob >= tiers["coin_flip_min"]:
        return "COIN_FLIP"
    return "NO_PICK"


def _cardio_category_weight(
    model_cfg: dict[str, Any],
    *,
    scheduled_rounds: int,
    is_title_fight: bool,
) -> float:
    by_rounds = model_cfg.get("cardio_weight_by_rounds") or {}
    if is_title_fight or scheduled_rounds >= 5:
        return float(by_rounds.get("five_round", 1.0))
    return float(by_rounds.get("three_round", 0.75))


def predict_fight(
    red_id: str,
    blue_id: str,
    red_name: str,
    blue_name: str,
    fighter_stats: dict[str, dict[str, Any]],
    weight_classes: dict[str, str | None],
    *,
    fight_id: int = 0,
    weight_class: str | None = None,
    model_cfg: dict[str, Any] | None = None,
    pool_by_weight_class: bool = True,
    scheduled_rounds: int = 3,
    is_title_fight: bool = False,
) -> FightPrediction:
    stats_cfg = load_stats_config()
    model_cfg = model_cfg or load_model_config()
    definitions = stats_cfg.get("stat_definitions", {})
    categories_cfg = stats_cfg["categories"]

    filled = impute_missing(fighter_stats, {}, weight_classes)
    normalized = normalize_fighter_stats(
        filled, weight_classes, definitions, pool_by_weight_class=pool_by_weight_class
    )
    cat_scores = category_scores(normalized, categories_cfg)

    weight_overrides = dict(model_cfg.get("category_weights") or {})
    cardio_base = float(
        weight_overrides.get("cardio", categories_cfg.get("cardio", {}).get("weight", 1.0))
    )
    cardio_mult = _cardio_category_weight(
        model_cfg,
        scheduled_rounds=scheduled_rounds,
        is_title_fight=is_title_fight,
    )
    if cardio_mult != 1.0:
        weight_overrides["cardio"] = cardio_base * cardio_mult

    temperature = float(model_cfg.get("temperature", 12.0))
    tiers = model_cfg["tiers"]
    bands = model_cfg["confidence_bands"]

    breakdowns: list[CategoryBreakdown] = []
    total_edge = 0.0
    weight_sum = 0.0

    for cat_name, cat in categories_cfg.items():
        w = float(weight_overrides.get(cat_name, cat.get("weight", 1.0)))
        red_s = cat_scores[red_id][cat_name]
        blue_s = cat_scores[blue_id][cat_name]
        gap = red_s - blue_s
        total_edge += gap * w
        weight_sum += w
        breakdowns.append(
            CategoryBreakdown(name=cat_name, red_score=red_s, blue_score=blue_s, gap=gap, weight=w)
        )

    if weight_sum > 0:
        total_edge /= weight_sum

    red_prob = _sigmoid(total_edge / temperature)
    blue_prob = 1.0 - red_prob

    if red_prob >= blue_prob:
        pick_corner, pick_name, win_prob = "red", red_name, red_prob
    else:
        pick_corner, pick_name, win_prob = "blue", blue_name, blue_prob

    tier = assign_tier(win_prob, tiers)
    band = float(bands.get(tier, 0.05))
    prob_low = max(0.01, win_prob - band)
    prob_high = min(0.99, win_prob + band)

    return FightPrediction(
        fight_id=fight_id,
        weight_class=weight_class,
        red_name=red_name,
        blue_name=blue_name,
        pick_name=pick_name,
        pick_corner=pick_corner,
        red_win_prob=red_prob,
        blue_win_prob=blue_prob,
        win_prob=win_prob,
        prob_low=prob_low,
        prob_high=prob_high,
        tier=tier,
        total_edge=total_edge,
        categories=breakdowns,
    )
