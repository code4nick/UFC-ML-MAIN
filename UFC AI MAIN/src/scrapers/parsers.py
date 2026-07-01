from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def extract_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def parse_height_inches(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"(\d+)'\s*(\d+)", raw)
    if not match:
        return None
    return int(match.group(1)) * 12 + int(match.group(2))


def parse_reach_inches(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"([\d.]+)", raw)
    return float(match.group(1)) if match else None


def parse_weight_lbs(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"([\d.]+)", raw)
    return float(match.group(1)) if match else None


def parse_percent(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"([\d.]+)", raw.strip())
    return float(match.group(1)) if match else None


def parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"([\d.]+)", raw.strip())
    return float(match.group(1)) if match else None


def parse_record(raw: str | None) -> tuple[int, int, int]:
    if not raw:
        return 0, 0, 0
    match = re.search(r"(\d+)-(\d+)-(\d+)", raw)
    if not match:
        return 0, 0, 0
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_dob(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = " ".join(raw.split())
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def age_from_dob(dob_iso: str | None, on_date: date | None = None) -> float | None:
    if not dob_iso:
        return None
    try:
        born = date.fromisoformat(dob_iso)
    except ValueError:
        return None
    today = on_date or date.today()
    years = today.year - born.year
    if (today.month, today.day) < (born.month, born.day):
        years -= 1
    return float(years) + (today - date(today.year, born.month, born.day)).days / 365.25


def parse_bout_line(text: str) -> tuple[str | None, bool, int]:
    """Parse a UFCStats bout line (e.g. 'Lightweight Title Bout') into class, title flag, rounds."""
    cleaned = text.replace("View Matchup", "").strip()
    if not cleaned:
        return None, False, 3
    lower = cleaned.lower()
    if "bout" not in lower and "weight" not in lower:
        return None, False, 3
    is_title = "title" in lower or "championship" in lower
    scheduled_rounds = 5 if is_title else 3
    return cleaned, is_title, scheduled_rounds


def parse_fight_detail_meta(soup: BeautifulSoup) -> dict[str, Any]:
    """Read weight class / title-bout flag from a fight detail page."""
    weight_class = None
    is_title = False
    scheduled_rounds = 3
    for col in soup.select("td.b-fight-details__table-col"):
        wc, title, rnds = parse_bout_line(col.get_text(" ", strip=True))
        if wc and "bout" in wc.lower():
            weight_class, is_title, scheduled_rounds = wc, title, rnds
            break
    if not weight_class:
        for el in soup.select("i.b-fight-details__fight-title, i.b-fight-details__text-item"):
            wc, title, rnds = parse_bout_line(el.get_text(" ", strip=True))
            if wc:
                weight_class, is_title, scheduled_rounds = wc, title, rnds
                break
    return {
        "weight_class": weight_class,
        "is_title_fight": is_title,
        "scheduled_rounds": scheduled_rounds,
    }


def parse_fight_time_seconds(round_num: int | None, time_str: str | None) -> float | None:
    if not round_num or not time_str:
        return None
    match = re.match(r"(\d+):(\d+)", time_str.strip())
    if not match:
        return None
    minutes, seconds = int(match.group(1)), int(match.group(2))
    return (round_num - 1) * 300 + minutes * 60 + seconds


# Per-fight sig strikes above this are almost certainly parse/cumulative errors.
MAX_SIG_STRIKES_PER_FIGHT = 400


def parse_strike_stat(raw: str | None) -> tuple[float | None, float | None]:
    """Parse '45 of 90' into landed, attempted."""
    if not raw:
        return None, None
    raw = " ".join(raw.split())
    if raw in {"---", ""}:
        return None, None
    match = re.search(r"(\d+)\s+of\s+(\d+)", raw, re.IGNORECASE)
    if match:
        landed = float(match.group(1))
        attempted = float(match.group(2))
        if (
            landed > MAX_SIG_STRIKES_PER_FIGHT
            or attempted > MAX_SIG_STRIKES_PER_FIGHT
            or landed > attempted
        ):
            return None, None
        return landed, attempted
    value = parse_float(raw)
    if value is None or value > MAX_SIG_STRIKES_PER_FIGHT:
        return None, None
    return value, None


def _fight_table_cell_text(col) -> str:
    """First fighter-specific cell value (avoids concatenating multiple <p> tags)."""
    parts = [p.get_text(strip=True) for p in col.select("p.b-fight-details__table-text")]
    parts = [p for p in parts if p and p != "---"]
    if parts:
        return parts[0]
    return col.get_text(strip=True)


def parse_td_stat(raw: str | None) -> float | None:
    if not raw:
        return None
    landed, _ = parse_strike_stat(raw)
    return landed


def parse_control_time_seconds(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw in {"---", ""}:
        return None
    match = re.match(r"(\d+):(\d+)", raw)
    if match:
        return float(int(match.group(1)) * 60 + int(match.group(2)))
    value = parse_float(raw)
    return value


def _box_list_value(soup: BeautifulSoup, label: str) -> str | None:
    for item in soup.select("li.b-list__box-list-item"):
        title = item.select_one("i.b-list__box-item-title")
        if not title:
            continue
        if label.lower() in title.get_text(strip=True).lower():
            text = item.get_text(" ", strip=True)
            text = text.replace(title.get_text(strip=True), "").strip()
            return text or None
    return None


def parse_upcoming_events(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    events: list[dict[str, Any]] = []
    for row in soup.select("tr.b-statistics__table-row"):
        link = row.select_one("a.b-link[href*='event-details']")
        if not link:
            continue
        name = link.get_text(strip=True)
        url = link["href"]
        date_cell = row.select_one("span.b-statistics__date")
        events.append(
            {
                "name": name,
                "url": url,
                "ufcstats_id": extract_id_from_url(url),
                "event_date": date_cell.get_text(strip=True) if date_cell else None,
            }
        )
    return events


def parse_event_page(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one("h2.b-content__title span.b-content__title-highlight")
    name = title_el.get_text(strip=True) if title_el else "Unknown Event"

    event_date = None
    location = None
    for item in soup.select("li.b-list__box-list-item"):
        label = item.select_one("i.b-list__box-item-title")
        if not label:
            continue
        label_text = label.get_text(strip=True)
        value = item.get_text(" ", strip=True).replace(label_text, "").strip()
        if label_text.startswith("Date"):
            event_date = value
        elif label_text.startswith("Location"):
            location = value

    fights: list[dict[str, Any]] = []
    for row in soup.select("tr.b-fight-details__table-row.b-fight-details__table-row__hover"):
        fight_url = row.get("data-link") or row.get("onclick", "")
        match = re.search(r"fight-details/[a-f0-9]+", fight_url)
        if not match:
            continue
        fight_path = match.group(0)
        fight_url = f"http://www.ufcstats.com/{fight_path}"

        fighter_links = row.select("a.b-link[href*='fighter-details']")
        if len(fighter_links) < 2:
            continue

        weight_class = None
        is_title = False
        scheduled_rounds = 3
        for col in row.select("td.b-fight-details__table-col"):
            wc, title, rnds = parse_bout_line(col.get_text(" ", strip=True))
            if wc and ("bout" in wc.lower() or "weight" in wc.lower()):
                weight_class, is_title, scheduled_rounds = wc, title, rnds

        fights.append(
            {
                "ufcstats_id": extract_id_from_url(fight_url),
                "url": fight_url,
                "fighter_red": {
                    "name": fighter_links[0].get_text(strip=True),
                    "url": fighter_links[0]["href"],
                    "ufcstats_id": extract_id_from_url(fighter_links[0]["href"]),
                },
                "fighter_blue": {
                    "name": fighter_links[1].get_text(strip=True),
                    "url": fighter_links[1]["href"],
                    "ufcstats_id": extract_id_from_url(fighter_links[1]["href"]),
                },
                "weight_class": weight_class,
                "is_title_fight": is_title,
                "scheduled_rounds": scheduled_rounds,
            }
        )

    return {
        "name": name,
        "event_date": event_date,
        "location": location,
        "fights": fights,
    }


def parse_fighter_page(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    name_el = soup.select_one("h2.b-content__title span.b-content__title-highlight")
    record_el = soup.select_one("span.b-content__title-record")
    nickname_el = soup.select_one("p.b-content__Nickname")

    wins, losses, draws = parse_record(record_el.get_text() if record_el else None)
    dob_raw = _box_list_value(soup, "DOB:")
    dob = parse_dob(dob_raw)
    stance = _box_list_value(soup, "STANCE:")

    career: dict[str, float | None] = {}
    label_map = {
        "SLpM:": "slpm",
        "Str. Acc.:": "str_acc",
        "SApM:": "sapm",
        "Str. Def:": "str_def",
        "TD Avg.:": "td_avg",
        "TD Acc.:": "td_acc",
        "TD Def.:": "td_def",
        "Sub. Avg.:": "sub_avg",
    }
    for label, key in label_map.items():
        raw = _box_list_value(soup, label)
        if key in {"str_acc", "str_def", "td_acc", "td_def"}:
            career[key] = parse_percent(raw)
        else:
            career[key] = parse_float(raw)

    fights: list[dict[str, Any]] = []
    for row in soup.select("tr.b-fight-details__table-row"):
        if "b-fight-details__table-row_type_first" in row.get("class", []):
            continue
        cols = row.select("td.b-fight-details__table-col")
        if len(cols) < 10:
            continue

        result = cols[0].get_text(strip=True)
        if result not in {"win", "loss", "draw", "nc"}:
            continue

        fight_url = row.get("data-link") or ""
        if not fight_url:
            onclick = row.get("onclick", "")
            match = re.search(r"fight-details/[a-f0-9]+", onclick)
            if match:
                fight_url = f"http://www.ufcstats.com/{match.group(0)}"

        opponent_link = cols[1].select_one("a")
        method = cols[7].get_text(" ", strip=True)
        round_raw = cols[8].get_text(strip=True)
        time_raw = cols[9].get_text(strip=True)
        round_num = int(round_raw) if round_raw.isdigit() else None

        kd = parse_float(_fight_table_cell_text(cols[2]))
        sig_landed, sig_attempted = parse_strike_stat(_fight_table_cell_text(cols[3]))
        td_landed = parse_td_stat(_fight_table_cell_text(cols[4]))
        sub_attempts = parse_float(_fight_table_cell_text(cols[5]))

        fights.append(
            {
                "result": result,
                "opponent": opponent_link.get_text(strip=True) if opponent_link else None,
                "opponent_url": opponent_link["href"] if opponent_link else None,
                "fight_url": fight_url or None,
                "kd": kd,
                "sig_strikes_landed": sig_landed,
                "sig_strikes_attempted": sig_attempted,
                "td_landed": td_landed,
                "sub_attempts": sub_attempts,
                "event": cols[6].get_text(" ", strip=True),
                "method": method,
                "round": round_num,
                "time": time_raw,
                "fight_time_seconds": parse_fight_time_seconds(round_num, time_raw),
            }
        )

    return {
        "name": name_el.get_text(strip=True) if name_el else "Unknown",
        "nickname": nickname_el.get_text(strip=True) if nickname_el else None,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "height_inches": parse_height_inches(_box_list_value(soup, "Height:")),
        "weight_lbs": parse_weight_lbs(_box_list_value(soup, "Weight:")),
        "reach_inches": parse_reach_inches(_box_list_value(soup, "Reach:")),
        "stance": stance,
        "dob": dob,
        "career": career,
        "fight_history": fights,
    }


def parse_fighter_record(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    record_el = soup.select_one("span.b-content__title-record")
    wins, losses, draws = parse_record(record_el.get_text() if record_el else None)
    total = wins + losses + draws
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": wins / total if total else None,
    }


def _column_values(col) -> list[str]:
    return [p.get_text(strip=True) for p in col.select("p.b-fight-details__table-text")]


def parse_fight_detail_totals(html: str) -> dict[str, Any]:
    """Parse totals table for both fighters on a fight detail page."""
    soup = BeautifulSoup(html, "lxml")
    event_link = soup.select_one("h2.b-content__title a[href*='event-details']")
    event_url = event_link["href"] if event_link else None
    event_name = event_link.get_text(strip=True) if event_link else None

    totals_table = None
    for section in soup.select("section.b-fight-details__section.js-fight-section"):
        table = section.select_one("table")
        if not table:
            continue
        headers = [th.get_text(strip=True) for th in table.select("th")]
        if "Rev." in headers and "Ctrl" in headers and headers and "Fighter" in headers[0]:
            totals_table = table
            break

    result: dict[str, Any] = {
        "event_url": event_url,
        "event_name": event_name,
        "fighters": {},
        **parse_fight_detail_meta(soup),
    }
    if not totals_table:
        return result

    rows = totals_table.select("tbody tr.b-fight-details__table-row")
    if not rows:
        return result

    cols = rows[0].select("td.b-fight-details__table-col")
    fighter_ids = [
        extract_id_from_url(a["href"])
        for a in cols[0].select("a[href*='fighter-details']")
    ]
    if len(fighter_ids) != 2:
        return result

    sig_values = _column_values(cols[2]) if len(cols) > 2 else ["", ""]
    rev_values = _column_values(cols[8]) if len(cols) > 8 else ["", ""]
    ctrl_values = _column_values(cols[9]) if len(cols) > 9 else ["", ""]

    for idx, fighter_id in enumerate(fighter_ids):
        opp_idx = 1 - idx
        sig_landed, _ = parse_strike_stat(sig_values[idx] if idx < len(sig_values) else None)
        opp_sig_landed, _ = parse_strike_stat(sig_values[opp_idx] if opp_idx < len(sig_values) else None)
        rev_raw = rev_values[idx] if idx < len(rev_values) else None
        ctrl_raw = ctrl_values[idx] if idx < len(ctrl_values) else None
        result["fighters"][fighter_id] = {
            "sig_strikes_landed": sig_landed,
            "sig_strikes_absorbed": opp_sig_landed,
            "reversals": parse_float(rev_raw),
            "ctrl_time_seconds": parse_control_time_seconds(ctrl_raw),
        }

    return result


def parse_fight_detail_page(html: str, fighter_ufcstats_id: str) -> dict[str, Any]:
    """Parse per-fight totals for one fighter from a fight detail page."""
    totals = parse_fight_detail_totals(html)
    fighter_stats = totals["fighters"].get(fighter_ufcstats_id, {})
    return {
        "event_url": totals.get("event_url"),
        "event_name": totals.get("event_name"),
        "sig_strikes_absorbed": fighter_stats.get("sig_strikes_absorbed"),
        "reversals": fighter_stats.get("reversals"),
        "ctrl_time_seconds": fighter_stats.get("ctrl_time_seconds"),
    }


def parse_event_date_only(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for item in soup.select("li.b-list__box-list-item"):
        label = item.select_one("i.b-list__box-item-title")
        if not label:
            continue
        if label.get_text(strip=True).startswith("Date"):
            return item.get_text(" ", strip=True).replace(label.get_text(strip=True), "").strip()
    return None
