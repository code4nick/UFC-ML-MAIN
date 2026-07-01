from __future__ import annotations

from datetime import date, datetime


def parse_ufc_event_date(raw: str | None) -> date | None:
    """Parse UFCStats dates like 'July 11, 2026'."""
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%B %d, %Y", "%B %d,%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
