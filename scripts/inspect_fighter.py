import json
import sqlite3
import sys

conn = sqlite3.connect("data/ufc_ai.db")
conn.row_factory = sqlite3.Row
name = sys.argv[1] if len(sys.argv) > 1 else "McGregor"
f = conn.execute(
    "SELECT id, name FROM fighters WHERE name LIKE ?", (f"%{name}%",)
).fetchone()
if not f:
    print("Fighter not found")
    raise SystemExit(1)

print("Fighter:", f["name"])
snap = conn.execute(
    """
    SELECT stats_json, missing_stats_json, scraped_at
    FROM fighter_stat_snapshots
    WHERE fighter_id = ?
    ORDER BY id DESC LIMIT 1
    """,
    (f["id"],),
).fetchone()
stats = json.loads(snap["stats_json"])
missing = json.loads(snap["missing_stats_json"])
print("scraped_at:", snap["scraped_at"])
print("Stats populated:", 47 - len(missing), "/ 47 | Missing:", len(missing))
print("Sample:", {k: stats[k] for k in ["slpm", "str_acc", "win_rate", "last_5_win_rate", "age_years", "sig_strikes_absorbed_per_fight", "reversals_per_fight", "opponent_avg_win_rate_in_wins"]})
if missing:
    print("Missing keys:", missing)
ctx = conn.execute(
    """
    SELECT context_json FROM fighter_context_snapshots
    WHERE fighter_id = ? AND scraped_at = ?
    LIMIT 1
    """,
    (f["id"], snap["scraped_at"]),
).fetchone()
if ctx:
    print("Context:", json.loads(ctx["context_json"]))
