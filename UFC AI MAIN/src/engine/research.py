from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import load_research_config
from src.engine.math_engine import FightPrediction, assign_tier, load_model_config


@dataclass
class ResearchResult:
    red_adjustment: float
    blue_adjustment: float
    why_pick: list[str] = field(default_factory=list)
    watch_out: list[str] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)


@dataclass
class BlendedPrediction:
    math: FightPrediction
    research: ResearchResult
    red_win_prob: float
    blue_win_prob: float
    pick_name: str
    pick_corner: str
    win_prob: float
    prob_low: float
    prob_high: float
    tier: str
    math_win_prob: float


def _get_context_value(context: dict[str, Any], field_name: str) -> Any:
    return context.get(field_name)


def _rule_matches(context: dict[str, Any], rule: dict[str, Any]) -> bool:
    field_name = rule.get("field")
    if not field_name:
        return False
    value = _get_context_value(context, field_name)
    if value is None:
        return False

    op = rule.get("operator", "eq")
    target = rule.get("value")
    max_val = rule.get("max_value")
    if op == "eq":
        return value == target
    if op == "gte":
        ok = float(value) >= float(target)
        if ok and max_val is not None:
            ok = float(value) <= float(max_val)
        return ok
    if op == "lte":
        return float(value) <= float(target)
    if op == "gt":
        return float(value) > float(target)
    if op == "lt":
        return float(value) < float(target)
    if op == "is_true":
        return bool(value) is True
    return False


def evaluate_research(
    red_context: dict[str, Any],
    blue_context: dict[str, Any],
    pick_corner: str,
    *,
    research_cfg: dict[str, Any] | None = None,
) -> ResearchResult:
    cfg = research_cfg or load_research_config()
    max_total = float(cfg.get("meta", {}).get("max_total_prob_adjustment", 0.05))
    per_side_cap = max_total / 2.0

    red_adj = 0.0
    blue_adj = 0.0
    why_pick: list[str] = []
    watch_out: list[str] = []
    fired: list[str] = []

    for rule in cfg.get("rules") or []:
        adj = float(rule.get("prob_adjustment", 0))
        bullet = rule.get("bullet", "")
        category = rule.get("category", "why_pick")
        applies_red = _rule_matches(red_context, rule)
        applies_blue = _rule_matches(blue_context, rule)

        if applies_red:
            red_adj += adj
            fired.append(str(rule.get("id", "rule")))
            target = why_pick if category == "why_pick" else watch_out
            if bullet:
                target.append(bullet)

        if applies_blue:
            blue_adj += adj
            fired.append(str(rule.get("id", "rule")))
            target = why_pick if category == "why_pick" else watch_out
            if bullet:
                target.append(bullet)

    red_adj = max(-per_side_cap, min(per_side_cap, red_adj))
    blue_adj = max(-per_side_cap, min(per_side_cap, blue_adj))

    return ResearchResult(
        red_adjustment=red_adj,
        blue_adjustment=blue_adj,
        why_pick=why_pick,
        watch_out=watch_out,
        rules_fired=fired,
    )


def _math_bullets(pred: FightPrediction) -> tuple[list[str], list[str]]:
    """Top category edges for why pick / watch out — math only, no research overlap."""
    why: list[str] = []
    watch: list[str] = []
    pick_is_red = pred.pick_corner == "red"

    ranked = sorted(pred.categories, key=lambda c: abs(c.gap), reverse=True)
    for cat in ranked[:3]:
        favors_red = cat.gap > 0
        favors_pick = favors_red == pick_is_red
        label = cat.name.replace("_", " ").title()
        leader = pred.red_name if favors_red else pred.blue_name
        text = f"{label}: {leader} +{abs(cat.gap):.1f}"
        if favors_pick:
            why.append(text)
        else:
            watch.append(text)

    return why, watch


def blend_prediction(
    math_pred: FightPrediction,
    red_context: dict[str, Any],
    blue_context: dict[str, Any],
) -> BlendedPrediction:
    model_cfg = load_model_config()
    tiers = model_cfg["tiers"]
    bands = model_cfg["confidence_bands"]

    research = evaluate_research(red_context, blue_context, math_pred.pick_corner)
    red_prob = max(0.01, min(0.99, math_pred.red_win_prob + research.red_adjustment))
    blue_prob = max(0.01, min(0.99, math_pred.blue_win_prob + research.blue_adjustment))
    total = red_prob + blue_prob
    red_prob /= total
    blue_prob /= total

    if red_prob >= blue_prob:
        pick_corner, pick_name, win_prob = "red", math_pred.red_name, red_prob
    else:
        pick_corner, pick_name, win_prob = "blue", math_pred.blue_name, blue_prob

    tier = assign_tier(win_prob, tiers)
    band = float(bands.get(tier, 0.05))
    prob_low = max(0.01, win_prob - band)
    prob_high = min(0.99, win_prob + band)

    math_why, math_watch = _math_bullets(math_pred)
    research.why_pick = math_why + research.why_pick
    research.watch_out = math_watch + research.watch_out

    return BlendedPrediction(
        math=math_pred,
        research=research,
        red_win_prob=red_prob,
        blue_win_prob=blue_prob,
        pick_name=pick_name,
        pick_corner=pick_corner,
        win_prob=win_prob,
        prob_low=prob_low,
        prob_high=prob_high,
        tier=tier,
        math_win_prob=math_pred.win_prob,
    )
