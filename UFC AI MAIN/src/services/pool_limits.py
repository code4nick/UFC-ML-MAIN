from __future__ import annotations

from src.config import MIN_DIVISION_POOL, MIN_DIVISION_POOL_CATCH, MIN_DIVISION_POOL_WOMENS

_CATCH_WEIGHT = "Catch Weight"


def min_pool_for_division(weight_class: str | None) -> int:
    """Minimum fighters for percentile pool — lower bar for thin UFC divisions."""
    if not weight_class:
        return MIN_DIVISION_POOL
    if weight_class == _CATCH_WEIGHT:
        return MIN_DIVISION_POOL_CATCH
    if weight_class.startswith("Women's"):
        return MIN_DIVISION_POOL_WOMENS
    return MIN_DIVISION_POOL
