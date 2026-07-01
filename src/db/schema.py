from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ufcstats_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    event_date TEXT,
    location TEXT,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fighters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ufcstats_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    nickname TEXT,
    height_inches REAL,
    weight_lbs REAL,
    reach_inches REAL,
    stance TEXT,
    dob TEXT,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ufcstats_id TEXT NOT NULL UNIQUE,
    event_id INTEGER NOT NULL REFERENCES events(id),
    fighter_red_id INTEGER NOT NULL REFERENCES fighters(id),
    fighter_blue_id INTEGER NOT NULL REFERENCES fighters(id),
    weight_class TEXT,
    is_title_fight INTEGER NOT NULL DEFAULT 0,
    scheduled_rounds INTEGER NOT NULL DEFAULT 3,
    winner_id INTEGER REFERENCES fighters(id),
    method TEXT,
    finish_round INTEGER,
    finish_time TEXT,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fighter_stat_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fighter_id INTEGER NOT NULL REFERENCES fighters(id),
    event_id INTEGER REFERENCES events(id),
    scraped_at TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    missing_stats_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (fighter_id, event_id, scraped_at)
);

CREATE TABLE IF NOT EXISTS fighter_context_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fighter_id INTEGER NOT NULL REFERENCES fighters(id),
    fight_id INTEGER NOT NULL REFERENCES fights(id),
    scraped_at TEXT NOT NULL,
    context_json TEXT NOT NULL,
    UNIQUE (fighter_id, fight_id, scraped_at)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fight_id INTEGER NOT NULL UNIQUE REFERENCES fights(id),
    event_id INTEGER NOT NULL REFERENCES events(id),
    pick_fighter_id INTEGER NOT NULL REFERENCES fighters(id),
    pick_name TEXT NOT NULL,
    pick_corner TEXT NOT NULL,
    math_prob REAL NOT NULL,
    final_prob REAL NOT NULL,
    tier TEXT NOT NULL,
    market_implied REAL,
    market_source TEXT,
    edge_points REAL,
    bet_verdict TEXT,
    pick_ml INTEGER,
    kelly_stake REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    units REAL,
    winner_name TEXT,
    method TEXT,
    graded_at TEXT,
    logged_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fights_event ON fights(event_id);
CREATE INDEX IF NOT EXISTS idx_stat_snapshots_fighter ON fighter_stat_snapshots(fighter_id);
CREATE INDEX IF NOT EXISTS idx_context_snapshots_fight ON fighter_context_snapshots(fight_id);
CREATE INDEX IF NOT EXISTS idx_predictions_event ON predictions(event_id);
CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
"""
