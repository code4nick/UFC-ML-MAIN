import json
import sqlite3

conn = sqlite3.connect("data/ufc_ai.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT f.name, s.missing_stats_json, s.scraped_at
    FROM fighter_stat_snapshots s
    JOIN fighters f ON f.id = s.fighter_id
    WHERE s.id IN (
        SELECT MAX(id) FROM fighter_stat_snapshots GROUP BY fighter_id
    )
    ORDER BY json_array_length(s.missing_stats_json) DESC, f.name
    """
).fetchall()

print("Latest snapshot per fighter:\n")
for r in rows:
    missing = json.loads(r["missing_stats_json"])
    populated = 47 - len(missing)
    print(f"  {r['name']}: {populated}/47 populated")
    if missing:
        print(f"    missing: {missing}")
