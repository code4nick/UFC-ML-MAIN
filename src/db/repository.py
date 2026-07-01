from __future__ import annotations

import json
import sqlite3
from datetime import date
from datetime import datetime, timezone
from typing import Any

from src.services.event_dates import parse_ufc_event_date


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_event(
        self,
        ufcstats_id: str,
        name: str,
        event_date: str | None,
        location: str | None,
        scraped_at: str,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO events (ufcstats_id, name, event_date, location, scraped_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ufcstats_id) DO UPDATE SET
                name = excluded.name,
                event_date = excluded.event_date,
                location = excluded.location,
                scraped_at = excluded.scraped_at
            """,
            (ufcstats_id, name, event_date, location, scraped_at),
        )
        row = self.conn.execute(
            "SELECT id FROM events WHERE ufcstats_id = ?", (ufcstats_id,)
        ).fetchone()
        return int(row["id"])

    def has_event(self, ufcstats_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM events WHERE ufcstats_id = ? LIMIT 1",
            (ufcstats_id,),
        ).fetchone()
        return row is not None

    def upsert_fighter(self, fighter: dict[str, Any], scraped_at: str) -> int:
        self.conn.execute(
            """
            INSERT INTO fighters (
                ufcstats_id, name, nickname, height_inches, weight_lbs,
                reach_inches, stance, dob, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ufcstats_id) DO UPDATE SET
                name = excluded.name,
                nickname = excluded.nickname,
                height_inches = excluded.height_inches,
                weight_lbs = excluded.weight_lbs,
                reach_inches = excluded.reach_inches,
                stance = excluded.stance,
                dob = excluded.dob,
                scraped_at = excluded.scraped_at
            """,
            (
                fighter["ufcstats_id"],
                fighter["name"],
                fighter.get("nickname"),
                fighter.get("height_inches"),
                fighter.get("weight_lbs"),
                fighter.get("reach_inches"),
                fighter.get("stance"),
                fighter.get("dob"),
                scraped_at,
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM fighters WHERE ufcstats_id = ?", (fighter["ufcstats_id"],)
        ).fetchone()
        return int(row["id"])

    def upsert_fight(self, fight: dict[str, Any], scraped_at: str) -> int:
        self.conn.execute(
            """
            INSERT INTO fights (
                ufcstats_id, event_id, fighter_red_id, fighter_blue_id,
                weight_class, is_title_fight, scheduled_rounds,
                winner_id, method, finish_round, finish_time, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ufcstats_id) DO UPDATE SET
                event_id = excluded.event_id,
                fighter_red_id = excluded.fighter_red_id,
                fighter_blue_id = excluded.fighter_blue_id,
                weight_class = excluded.weight_class,
                is_title_fight = excluded.is_title_fight,
                scheduled_rounds = excluded.scheduled_rounds,
                winner_id = excluded.winner_id,
                method = excluded.method,
                finish_round = excluded.finish_round,
                finish_time = excluded.finish_time,
                scraped_at = excluded.scraped_at
            """,
            (
                fight["ufcstats_id"],
                fight["event_id"],
                fight["fighter_red_id"],
                fight["fighter_blue_id"],
                fight.get("weight_class"),
                int(fight.get("is_title_fight", False)),
                fight.get("scheduled_rounds", 3),
                fight.get("winner_id"),
                fight.get("method"),
                fight.get("finish_round"),
                fight.get("finish_time"),
                scraped_at,
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM fights WHERE ufcstats_id = ?", (fight["ufcstats_id"],)
        ).fetchone()
        return int(row["id"])

    def save_stat_snapshot(
        self,
        fighter_id: int,
        event_id: int,
        stats: dict[str, Any],
        missing: list[str],
        scraped_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO fighter_stat_snapshots (
                fighter_id, event_id, scraped_at, stats_json, missing_stats_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                fighter_id,
                event_id,
                scraped_at,
                json.dumps(stats, sort_keys=True),
                json.dumps(missing),
            ),
        )

    def save_context_snapshot(
        self,
        fighter_id: int,
        fight_id: int,
        context: dict[str, Any],
        scraped_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO fighter_context_snapshots (
                fighter_id, fight_id, scraped_at, context_json
            ) VALUES (?, ?, ?, ?)
            """,
            (fighter_id, fight_id, scraped_at, json.dumps(context, sort_keys=True)),
        )

    def summary(self) -> dict[str, Any]:
        counts = {}
        for table in ("events", "fighters", "fights", "fighter_stat_snapshots", "fighter_context_snapshots"):
            row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
            counts[table] = row["c"]
        latest_event = self.conn.execute(
            """
            SELECT name, event_date, scraped_at
            FROM events
            ORDER BY event_date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return {"counts": counts, "latest_event": dict(latest_event) if latest_event else None}

    def get_latest_event(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, ufcstats_id, name, event_date, location, scraped_at
            FROM events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def get_upcoming_event(self) -> dict[str, Any] | None:
        """Nearest future card with no recorded fight results (the card to lock picks for)."""
        rows = self.conn.execute(
            """
            SELECT e.id, e.ufcstats_id, e.name, e.event_date, e.location, e.scraped_at
            FROM events e
            WHERE EXISTS (SELECT 1 FROM fights f WHERE f.event_id = e.id)
              AND NOT EXISTS (
                  SELECT 1 FROM fights f
                  WHERE f.event_id = e.id AND f.winner_id IS NOT NULL
              )
            """
        ).fetchall()
        if not rows:
            return None

        today = date.today()
        future: list[tuple[date, dict[str, Any]]] = []
        dated: list[tuple[date, dict[str, Any]]] = []
        undated: list[dict[str, Any]] = []

        for row in rows:
            event = dict(row)
            parsed = parse_ufc_event_date(event.get("event_date"))
            if parsed is None:
                undated.append(event)
            elif parsed >= today:
                future.append((parsed, event))
            else:
                dated.append((parsed, event))

        if future:
            future.sort(key=lambda item: item[0])
            return future[0][1]

        if dated:
            dated.sort(key=lambda item: item[0], reverse=True)
            return dated[0][1]

        if undated:
            return undated[-1]

        return None

    def get_event_by_name(self, name_part: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, ufcstats_id, name, event_date, location, scraped_at
            FROM events
            WHERE lower(name) LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"%{name_part.lower()}%",),
        ).fetchone()
        return dict(row) if row else None

    def get_event_fights(self, event_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                f.id AS fight_id,
                f.weight_class,
                f.is_title_fight,
                f.scheduled_rounds,
                fr.id AS red_id,
                fr.name AS red_name,
                fr.ufcstats_id AS red_ufcstats_id,
                fb.id AS blue_id,
                fb.name AS blue_name,
                fb.ufcstats_id AS blue_ufcstats_id
            FROM fights f
            JOIN fighters fr ON fr.id = f.fighter_red_id
            JOIN fighters fb ON fb.id = f.fighter_blue_id
            WHERE f.event_id = ?
            ORDER BY f.id
            """,
            (event_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_fighters_with_stats(self) -> list[dict[str, Any]]:
        """Fighters that have at least one stat snapshot (latest per fighter)."""
        rows = self.conn.execute(
            """
            SELECT
                f.id AS fighter_id,
                f.name,
                f.ufcstats_id,
                s.stats_json,
                s.missing_stats_json,
                s.scraped_at
            FROM fighters f
            INNER JOIN fighter_stat_snapshots s ON s.fighter_id = f.id
            WHERE s.id = (
                SELECT MAX(s2.id) FROM fighter_stat_snapshots s2
                WHERE s2.fighter_id = f.id
            )
            ORDER BY f.name COLLATE NOCASE
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            stats = json.loads(row["stats_json"])
            result.append(
                {
                    "fighter_id": int(row["fighter_id"]),
                    "name": row["name"],
                    "ufcstats_id": row["ufcstats_id"],
                    "stats": stats,
                    "missing": json.loads(row["missing_stats_json"]),
                    "scraped_at": row["scraped_at"],
                }
            )
        return result

    def get_recent_event_ids(self, limit: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT id FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [int(r["id"]) for r in rows]

    def get_pool_event_ids(self, limit: int) -> list[int]:
        """Last N events by ingest order, plus the upcoming card if it fell outside that window."""
        event_ids = self.get_recent_event_ids(limit)
        upcoming = self.get_upcoming_event()
        if upcoming:
            uid = int(upcoming["id"])
            if uid not in event_ids:
                event_ids.append(uid)
        return event_ids

    def get_fighter_ids_from_recent_events(self, event_limit: int) -> set[int]:
        event_ids = self.get_pool_event_ids(event_limit)
        if not event_ids:
            return set()
        placeholders = ",".join("?" * len(event_ids))
        rows = self.conn.execute(
            f"""
            SELECT fighter_red_id AS fighter_id FROM fights WHERE event_id IN ({placeholders})
            UNION
            SELECT fighter_blue_id AS fighter_id FROM fights WHERE event_id IN ({placeholders})
            """,
            event_ids + event_ids,
        ).fetchall()
        return {int(r["fighter_id"]) for r in rows}

    def division_pool_counts(self, event_limit: int) -> dict[str, int]:
        """Fighters per normalized weight class in the last N-card pool."""
        from src.services.weight_class import normalize_weight_class

        fighter_ids = self.get_fighter_ids_from_recent_events(event_limit)
        if not fighter_ids:
            return {}
        wc_map = self.get_latest_weight_classes()
        counts: dict[str, int] = {}
        for fid in fighter_ids:
            wc = normalize_weight_class(wc_map.get(fid))
            if wc:
                counts[wc] = counts.get(wc, 0) + 1
        return counts

    def thin_divisions(self, event_limit: int) -> dict[str, int]:
        from src.services.pool_limits import min_pool_for_division

        counts = self.division_pool_counts(event_limit)
        return {
            wc: n
            for wc, n in counts.items()
            if n < min_pool_for_division(wc)
        }

    def get_latest_weight_classes(self) -> dict[int, str | None]:
        rows = self.conn.execute(
            """
            WITH fighter_fights AS (
                SELECT fighter_red_id AS fighter_id, weight_class, id AS fight_id FROM fights
                UNION ALL
                SELECT fighter_blue_id, weight_class, id FROM fights
            ),
            ranked AS (
                SELECT fighter_id, weight_class,
                       ROW_NUMBER() OVER (PARTITION BY fighter_id ORDER BY fight_id DESC) AS rn
                FROM fighter_fights
            )
            SELECT fighter_id, weight_class FROM ranked WHERE rn = 1
            """
        ).fetchall()
        return {int(r["fighter_id"]): r["weight_class"] for r in rows}

    def get_latest_context_for_fighter(self, fighter_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT context_json FROM fighter_context_snapshots
            WHERE fighter_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (fighter_id,),
        ).fetchone()
        if not row:
            return {}
        return json.loads(row["context_json"])

    def get_latest_stats_for_event(self, event_id: int) -> dict[int, dict[str, Any]]:
        """fighter_id -> {stats, missing, name, ufcstats_id}"""
        rows = self.conn.execute(
            """
            SELECT
                f.id AS fighter_id,
                f.name,
                f.ufcstats_id,
                s.stats_json,
                s.missing_stats_json
            FROM fighter_stat_snapshots s
            JOIN fighters f ON f.id = s.fighter_id
            WHERE s.event_id = ?
              AND s.id IN (
                  SELECT MAX(id) FROM fighter_stat_snapshots
                  WHERE event_id = ? GROUP BY fighter_id
              )
            """,
            (event_id, event_id),
        ).fetchall()
        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            result[row["fighter_id"]] = {
                "name": row["name"],
                "ufcstats_id": row["ufcstats_id"],
                "stats": json.loads(row["stats_json"]),
                "missing": json.loads(row["missing_stats_json"]),
            }
        return result

    def get_latest_contexts_for_event(self, event_id: int) -> dict[tuple[int, int], dict[str, Any]]:
        """Map (fight_id, fighter_id) -> context dict."""
        rows = self.conn.execute(
            """
            SELECT c.fight_id, c.fighter_id, c.context_json
            FROM fighter_context_snapshots c
            WHERE c.id IN (
                SELECT MAX(c2.id)
                FROM fighter_context_snapshots c2
                JOIN fights f ON f.id = c2.fight_id
                WHERE f.event_id = ?
                GROUP BY c2.fight_id, c2.fighter_id
            )
            """,
            (event_id,),
        ).fetchall()

        return {
            (int(r["fight_id"]), int(r["fighter_id"])): json.loads(r["context_json"])
            for r in rows
        }

    def prediction_exists_for_fight(self, fight_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM predictions WHERE fight_id = ?", (fight_id,)
        ).fetchone()
        return row is not None

    def insert_prediction(self, **fields: Any) -> int:
        cols = list(fields.keys())
        placeholders = ", ".join("?" * len(cols))
        col_names = ", ".join(cols)
        self.conn.execute(
            f"INSERT INTO predictions ({col_names}) VALUES ({placeholders})",
            tuple(fields[c] for c in cols),
        )
        row = self.conn.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])

    def get_pending_predictions(self, event_name: str | None = None) -> list[dict[str, Any]]:
        if event_name:
            rows = self.conn.execute(
                """
                SELECT p.* FROM predictions p
                JOIN events e ON e.id = p.event_id
                WHERE p.status = 'pending' AND lower(e.name) LIKE ?
                """,
                (f"%{event_name.lower()}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM predictions WHERE status = 'pending'"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_fight_result(self, fight_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                f.id, f.winner_id, f.method, f.finish_round, f.finish_time,
                w.name AS winner_name
            FROM fights f
            LEFT JOIN fighters w ON w.id = f.winner_id
            WHERE f.id = ?
            """,
            (fight_id,),
        ).fetchone()
        return dict(row) if row else None

    def grade_prediction(
        self,
        prediction_id: int,
        status: str,
        units: float,
        winner_name: str,
        method: str | None,
        graded_at: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE predictions
            SET status = ?, units = ?, winner_name = ?, method = ?, graded_at = ?
            WHERE id = ?
            """,
            (status, units, winner_name, method, graded_at, prediction_id),
        )

    def get_lifetime_record(self) -> "LifetimeRecord":
        from src.engine.grading import LifetimeRecord

        row = self.conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'win' THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN status = 'loss' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'push' THEN 1 ELSE 0 END) AS pushes,
                COALESCE(SUM(CASE WHEN status IN ('win', 'loss') THEN units ELSE 0 END), 0) AS units
            FROM predictions
            """
        ).fetchone()
        return LifetimeRecord(
            wins=int(row["wins"] or 0),
            losses=int(row["losses"] or 0),
            pending=int(row["pending"] or 0),
            pushes=int(row["pushes"] or 0),
            units=float(row["units"] or 0.0),
        )

    def get_graded_predictions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                p.pick_name, p.final_prob, p.tier, p.status, p.units,
                p.winner_name, p.method, p.graded_at, p.logged_at,
                p.bet_verdict, p.edge_points,
                e.name AS event_name,
                fr.name AS red_name, fb.name AS blue_name
            FROM predictions p
            JOIN events e ON e.id = p.event_id
            JOIN fights f ON f.id = p.fight_id
            JOIN fighters fr ON fr.id = f.fighter_red_id
            JOIN fighters fb ON fb.id = f.fighter_blue_id
            WHERE p.status IN ('win', 'loss')
            ORDER BY p.graded_at DESC, p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_event_predictions(self, event_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                p.*, fr.name AS red_name, fb.name AS blue_name
            FROM predictions p
            JOIN fights f ON f.id = p.fight_id
            JOIN fighters fr ON fr.id = f.fighter_red_id
            JOIN fighters fb ON fb.id = f.fighter_blue_id
            WHERE p.event_id = ?
            ORDER BY p.id
            """,
            (event_id,),
        ).fetchall()
        return [dict(r) for r in rows]
