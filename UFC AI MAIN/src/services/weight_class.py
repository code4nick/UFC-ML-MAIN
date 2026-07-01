from __future__ import annotations


def normalize_weight_class(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.replace("Bout", "").strip() or None
