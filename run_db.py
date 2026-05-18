"""
SQLite 本地跑步数据存储
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "runs.db")


def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            label_id TEXT PRIMARY KEY,
            sport_type INTEGER,
            start_time TEXT,
            duration_sec REAL,
            distance_km REAL,
            pace_min_per_km REAL,
            avg_hr_bpm INTEGER,
            max_hr_bpm INTEGER,
            avg_cadence REAL,
            avg_stride_length_cm REAL,
            avg_vertical_oscillation_mm REAL,
            avg_ground_time_ms REAL,
            calories INTEGER,
            ascent_m REAL,
            descent_m REAL,
            avg_power_w REAL,
            training_load REAL,
            training_effect REAL,
            evolab_data TEXT,
            summary_json TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS hr_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label_id TEXT,
            zone_name TEXT,
            count INTEGER,
            pct REAL,
            FOREIGN KEY (label_id) REFERENCES runs(label_id)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_time ON runs(start_time DESC);
    """)


def save_run(label_id: str, sport_type: int, summary: dict, hr_zones: dict,
             evolab_data: dict = None):
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO runs
            (label_id, sport_type, start_time, duration_sec, distance_km,
             pace_min_per_km, avg_hr_bpm, max_hr_bpm, avg_cadence,
             avg_stride_length_cm, avg_vertical_oscillation_mm,
             avg_ground_time_ms, calories, ascent_m, descent_m,
             avg_power_w, training_load, training_effect,
             evolab_data, summary_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        label_id, sport_type, summary.get("start_time"),
        summary.get("duration_sec"), summary.get("distance_km"),
        summary.get("pace_min_per_km"), summary.get("avg_hr_bpm"),
        summary.get("max_hr_bpm"), summary.get("avg_cadence"),
        summary.get("avg_stride_length_cm"),
        summary.get("avg_vertical_oscillation_mm"),
        summary.get("avg_ground_time_ms"),
        summary.get("calories"), summary.get("ascent_m"),
        summary.get("descent_m"),
        summary.get("avg_power_w"),
        summary.get("training_load"),
        summary.get("training_effect"),
        json.dumps(evolab_data, ensure_ascii=False) if evolab_data else None,
        json.dumps(summary, ensure_ascii=False),
    ))
    conn.execute("DELETE FROM hr_zones WHERE label_id=?", (label_id,))
    for name, data in hr_zones.items():
        conn.execute("INSERT INTO hr_zones (label_id, zone_name, count, pct) VALUES (?,?,?,?)",
                     (label_id, name, data["count"], data["pct"]))
    conn.commit()
    conn.close()


def get_run(label_id: str) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM runs WHERE label_id=?", (label_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_runs(limit=30) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY start_time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trends() -> dict:
    """计算跑步趋势数据"""
    conn = get_db()
    rows = conn.execute("""
        SELECT start_time, distance_km, pace_min_per_km, avg_hr_bpm,
               duration_sec, training_effect
        FROM runs
        WHERE start_time IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 100
    """).fetchall()
    conn.close()

    if not rows:
        return {"message": "暂无跑步数据"}

    distances = []
    paces = []
    hrs = []
    weeks = {}

    for r in reversed(rows):
        d = dict(r)
        if d["distance_km"]:
            distances.append(d["distance_km"])
        if d["pace_min_per_km"]:
            paces.append(d["pace_min_per_km"])
        if d["avg_hr_bpm"]:
            hrs.append(d["avg_hr_bpm"])
        if d["start_time"]:
            week = d["start_time"][:7]  # YYYY-MM
            prev = weeks.get(week, {"runs": 0, "distance": 0, "duration": 0})
            prev["runs"] += 1
            prev["distance"] += d["distance_km"] or 0
            prev["duration"] += (d["duration_sec"] or 0) / 60
            weeks[week] = prev

    return {
        "total_runs": len(rows),
        "avg_distance_km": round(sum(distances) / len(distances), 2) if distances else 0,
        "avg_pace_min_per_km": round(sum(paces) / len(paces), 2) if paces else 0,
        "avg_hr_bpm": round(sum(hrs) / len(hrs)) if hrs else 0,
        "best_pace": round(min(paces), 2) if paces else None,
        "longest_run_km": round(max(distances), 2) if distances else 0,
        "weekly_summary": weeks,
    }
