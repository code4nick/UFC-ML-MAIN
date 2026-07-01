from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "ufc_ai.db"
# Completed cards used for rolling percentile pools (ingest once, then --upcoming only).
DEFAULT_ROSTER_CARDS = 10
# Expand --last-cards until each division in the pool has at least this many fighters.
MIN_DIVISION_POOL = 20
MIN_DIVISION_POOL_WOMENS = 8
MIN_DIVISION_POOL_CATCH = 6
ROSTER_CARD_STEP = 5
MAX_ROSTER_CARDS = 60


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_stats_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "stats.yaml")


def load_research_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "research_rules.yaml")


def load_model_config() -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / "model.yaml")


def all_math_stat_keys() -> list[str]:
    cfg = load_stats_config()
    keys: list[str] = []
    for cat in cfg["categories"].values():
        keys.extend(cat["stats"])
    return keys
