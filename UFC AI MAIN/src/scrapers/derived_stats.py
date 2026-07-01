from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.config import all_math_stat_keys
from src.scrapers.parsers import MAX_SIG_STRIKES_PER_FIGHT


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0):
        return None
    return num / den


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def _parse_event_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _is_finish_win(method: str | None) -> bool:
    if not method:
        return False
    m = method.lower()
    return "ko" in m or "tko" in m or "submission" in m


def _is_ko_win(method: str | None) -> bool:
    if not method:
        return False
    m = method.lower()
    return "ko" in m or "tko" in m


def _is_sub_win(method: str | None) -> bool:
    return bool(method and "submission" in method.lower())


def _is_decision(method: str | None) -> bool:
    return bool(method and "decision" in method.lower())


def _is_finish_loss(method: str | None) -> bool:
    return _is_finish_win(method)


def _fight_strike_rate_per_min(fight: dict[str, Any]) -> float | None:
    sig = fight.get("sig_strikes_landed")
    time_sec = fight.get("fight_time_seconds")
    if sig is None or not time_sec or time_sec <= 0:
        return None
    landed = float(sig)
    if landed < 0 or landed > MAX_SIG_STRIKES_PER_FIGHT:
        return None
    return landed / (float(time_sec) / 60.0)


def _fight_ctrl_rate_per_min(fight: dict[str, Any]) -> float | None:
    ctrl = fight.get("ctrl_time_seconds")
    time_sec = fight.get("fight_time_seconds")
    if ctrl is None or not time_sec or time_sec <= 0:
        return None
    return float(ctrl) / (float(time_sec) / 60.0)


def _is_deep_fight(fight: dict[str, Any]) -> bool:
    rnd = fight.get("round")
    time_sec = fight.get("fight_time_seconds")
    if rnd is not None and int(rnd) >= 3:
        return True
    return time_sec is not None and float(time_sec) >= 600


def _is_early_fight(fight: dict[str, Any]) -> bool:
    rnd = fight.get("round")
    time_sec = fight.get("fight_time_seconds")
    if rnd is not None and int(rnd) <= 1:
        return True
    return time_sec is not None and float(time_sec) < 420


def compute_derived_stats(
    fighter: dict[str, Any],
    reference_date: date | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Build all 47 math stats. Returns (stats, missing_keys)."""
    ref = reference_date or date.today()
    career = fighter.get("career", {})
    history: list[dict[str, Any]] = fighter.get("fight_history", [])
    wins = int(fighter.get("wins", 0))
    losses = int(fighter.get("losses", 0))
    draws = int(fighter.get("draws", 0))
    total_fights = wins + losses + draws

    stats: dict[str, Any] = {
        "slpm": career.get("slpm"),
        "str_acc": career.get("str_acc"),
        "sapm": career.get("sapm"),
        "str_def": career.get("str_def"),
        "td_avg": career.get("td_avg"),
        "td_acc": career.get("td_acc"),
        "td_def": career.get("td_def"),
        "sub_avg": career.get("sub_avg"),
        "height_inches": fighter.get("height_inches"),
        "reach_inches": fighter.get("reach_inches"),
        "weight_lbs": fighter.get("weight_lbs"),
        "wins": float(wins),
        "losses": float(losses),
        "draws": float(draws),
        "southpaw_flag": 1.0 if (fighter.get("stance") or "").lower() == "southpaw" else 0.0,
    }

    dob = fighter.get("dob")
    if dob:
        try:
            born = date.fromisoformat(dob)
            stats["age_years"] = ref.year - born.year - (
                (ref.month, ref.day) < (born.month, born.day)
            )
        except ValueError:
            stats["age_years"] = None
    else:
        stats["age_years"] = None

    stats["win_rate"] = _rate(wins, total_fights)
    stats["total_fights"] = float(total_fights)
    stats["ufc_fight_count"] = float(len(history))

    raw_win_rate = stats["win_rate"]
    ufc_fights = len(history)
    if raw_win_rate is not None and ufc_fights > 0:
        prior_rate = 0.5
        prior_ufc_fights = 4.0
        stats["win_rate"] = (
            float(raw_win_rate) * ufc_fights + prior_rate * prior_ufc_fights
        ) / (ufc_fights + prior_ufc_fights)

    finish_wins = ko_wins = sub_wins = dec_wins = dec_losses = 0
    finish_losses = ko_losses = sub_losses = 0
    first_round_finishes = 0
    title_fight_wins = 0

    sig_landed_list: list[float] = []
    sig_absorbed_list: list[float] = []
    td_list: list[float] = []
    kd_list: list[float] = []
    sub_list: list[float] = []
    rev_list: list[float] = []
    ctrl_list: list[float] = []
    fight_times: list[float] = []
    rounds_list: list[float] = []
    opponent_rates: list[float] = []
    opponent_rates_in_wins: list[float] = []
    early_strike_rates: list[float] = []
    deep_strike_rates: list[float] = []
    early_ctrl_rates: list[float] = []
    deep_ctrl_rates: list[float] = []

    for fight in history:
        method = fight.get("method")
        result = fight.get("result")
        if result == "win":
            if _is_finish_win(method):
                finish_wins += 1
            if _is_ko_win(method):
                ko_wins += 1
            if _is_sub_win(method):
                sub_wins += 1
            if _is_decision(method):
                dec_wins += 1
            if fight.get("round") == 1 and _is_finish_win(method):
                first_round_finishes += 1
            if fight.get("is_title_fight"):
                title_fight_wins += 1
        elif result == "loss":
            if _is_finish_loss(method):
                finish_losses += 1
            if _is_ko_win(method):
                ko_losses += 1
            if _is_sub_win(method):
                sub_losses += 1
            if _is_decision(method):
                dec_losses += 1

        sig_landed = fight.get("sig_strikes_landed")
        if sig_landed is not None:
            landed_val = float(sig_landed)
            if 0 <= landed_val <= MAX_SIG_STRIKES_PER_FIGHT:
                sig_landed_list.append(landed_val)
        if fight.get("td_landed") is not None:
            td_list.append(float(fight["td_landed"]))
        if fight.get("kd") is not None:
            kd_list.append(float(fight["kd"]))
        if fight.get("sub_attempts") is not None:
            sub_list.append(float(fight["sub_attempts"]))
        if fight.get("sig_strikes_absorbed") is not None:
            sig_absorbed_list.append(float(fight["sig_strikes_absorbed"]))
        if fight.get("reversals") is not None:
            rev_list.append(float(fight["reversals"]))
        if fight.get("ctrl_time_seconds") is not None:
            ctrl_list.append(float(fight["ctrl_time_seconds"]))
        if fight.get("opponent_win_rate") is not None:
            opp_rate = float(fight["opponent_win_rate"])
            opponent_rates.append(opp_rate)
            if result == "win":
                opponent_rates_in_wins.append(opp_rate)
        if fight.get("fight_time_seconds") is not None:
            fight_times.append(float(fight["fight_time_seconds"]))
        if fight.get("round") is not None:
            rounds_list.append(float(fight["round"]))

        rate = _fight_strike_rate_per_min(fight)
        if rate is not None:
            if _is_early_fight(fight):
                early_strike_rates.append(rate)
            if _is_deep_fight(fight):
                deep_strike_rates.append(rate)

        ctrl_rate = _fight_ctrl_rate_per_min(fight)
        if ctrl_rate is not None:
            if _is_early_fight(fight):
                early_ctrl_rates.append(ctrl_rate)
            if _is_deep_fight(fight):
                deep_ctrl_rates.append(ctrl_rate)

    stats["finish_rate"] = _rate(finish_wins, max(wins, 1))
    stats["ko_tko_win_rate"] = _rate(ko_wins, max(wins, 1))
    stats["submission_win_rate"] = _rate(sub_wins, max(wins, 1))
    stats["decision_win_rate"] = _rate(dec_wins, max(wins, 1))
    decision_fights = dec_wins + dec_losses
    stats["decision_fight_win_rate"] = _rate(dec_wins, decision_fights)
    stats["first_round_finish_rate"] = _rate(first_round_finishes, max(wins, 1))
    stats["title_fight_wins"] = float(title_fight_wins)

    stats["finish_loss_rate"] = _rate(finish_losses, max(losses, 1))
    stats["ko_tko_loss_rate"] = _rate(ko_losses, max(losses, 1))
    stats["sub_loss_rate"] = _rate(sub_losses, max(losses, 1))

    stats["sig_strikes_landed_per_fight"] = _mean(sig_landed_list)
    stats["sig_strikes_absorbed_per_fight"] = _mean(sig_absorbed_list)
    stats["td_landed_per_fight"] = _mean(td_list)
    stats["kd_per_fight"] = _mean(kd_list)
    stats["sub_attempts_per_fight"] = _mean(sub_list)
    stats["reversals_per_fight"] = _mean(rev_list)
    stats["ctrl_time_per_fight_seconds"] = _mean(ctrl_list)
    stats["avg_fight_time_seconds"] = _mean(fight_times)
    stats["avg_rounds_fought"] = _mean(rounds_list)
    stats["opponent_avg_win_rate"] = _mean(opponent_rates)
    stats["opponent_avg_win_rate_in_wins"] = _mean(opponent_rates_in_wins)

    early_strike_pace = _mean(early_strike_rates)
    late_strike_pace = _mean(deep_strike_rates)
    stats["sig_strikes_per_minute_late"] = late_strike_pace
    if early_strike_pace and early_strike_pace > 0 and late_strike_pace is not None:
        stats["pace_decay_ratio"] = float(late_strike_pace) / float(early_strike_pace)
    else:
        stats["pace_decay_ratio"] = None

    early_ctrl_pace = _mean(early_ctrl_rates)
    late_ctrl_pace = _mean(deep_ctrl_rates)
    if early_ctrl_pace and early_ctrl_pace > 0 and late_ctrl_pace is not None:
        stats["grappling_pace_decay_ratio"] = float(late_ctrl_pace) / float(early_ctrl_pace)
    else:
        stats["grappling_pace_decay_ratio"] = None

    # Last 5 fights
    last5 = history[:5]
    l5_wins = sum(1 for f in last5 if f.get("result") == "win")
    l5_finishes = sum(1 for f in last5 if f.get("result") == "win" and _is_finish_win(f.get("method")))
    stats["last_5_win_rate"] = _rate(l5_wins, len(last5)) if last5 else None
    stats["last_5_finish_rate"] = _rate(l5_finishes, len(last5)) if last5 else None

    win_streak = loss_streak = 0
    for fight in history:
        if fight.get("result") == "win":
            if loss_streak:
                break
            win_streak += 1
        elif fight.get("result") == "loss":
            if win_streak:
                break
            loss_streak += 1
        else:
            break
    stats["win_streak"] = float(win_streak)
    stats["loss_streak"] = float(loss_streak)

    decisions = sum(1 for f in history if _is_decision(f.get("method")))
    stats["decision_rate"] = _rate(decisions, len(history)) if history else None

    slpm = stats.get("slpm")
    str_acc = stats.get("str_acc")
    sapm = stats.get("sapm")
    str_def = stats.get("str_def")
    if None not in (slpm, str_acc, sapm, str_def):
        landed_proxy = float(slpm) * (float(str_acc) / 100.0)
        absorbed_proxy = float(sapm) * (1.0 - float(str_def) / 100.0)
        stats["striking_differential"] = landed_proxy - absorbed_proxy
    else:
        stats["striking_differential"] = None

    td_avg = stats.get("td_avg")
    td_def = stats.get("td_def")
    if td_avg is not None and td_def is not None:
        stats["takedown_margin"] = float(td_avg) * (float(td_def) / 100.0)
    else:
        stats["takedown_margin"] = None

    height = stats.get("height_inches")
    reach = stats.get("reach_inches")
    stats["reach_per_inch_height"] = _safe_div(reach, height)

    finish_loss = stats.get("finish_loss_rate")
    stats["chin_score"] = None if finish_loss is None else max(0.0, 1.0 - float(finish_loss))

    missing = [k for k in all_math_stat_keys() if stats.get(k) is None]
    return stats, missing


def build_research_context(
    fighter: dict[str, Any],
    fight_meta: dict[str, Any],
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Context-only fields for Step 5 rules — no math stat keys."""
    ref = reference_date or date.today()
    history: list[dict[str, Any]] = fighter.get("fight_history", [])
    ufc_fight_count = len(history)

    days_since_last = None
    months_since_last = None
    if history:
        last_fight = history[0]
        last_date = _parse_event_date(last_fight.get("event_date"))
        if last_date:
            days_since_last = (ref - last_date).days
            months_since_last = round(days_since_last / 30.44, 1)

    return {
        "days_since_last_fight": days_since_last,
        "months_since_last_fight": months_since_last,
        "is_ufc_debut_on_card": ufc_fight_count == 0,
        "is_title_fight": bool(fight_meta.get("is_title_fight")),
        "scheduled_rounds": int(fight_meta.get("scheduled_rounds", 3)),
        "short_notice_days": None,
        "weight_miss_last_card": None,
        "returning_from_injury_flag": None,
    }
