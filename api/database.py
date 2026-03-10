"""
Fantasy Baseball Keeper League - PostgreSQL Database Setup
"""
from __future__ import annotations

import json
import os
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/keeper_league",
)

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        yahoo_guid TEXT UNIQUE NOT NULL,
        yahoo_nickname TEXT,
        yahoo_email TEXT,
        team_id INTEGER,
        is_commissioner INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        last_login TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS teams (
        id SERIAL PRIMARY KEY,
        manager_name TEXT NOT NULL UNIQUE,
        team_name TEXT,
        yahoo_team_id TEXT,
        trade_compensation INTEGER DEFAULT 0,
        faab_adjustment INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_snapshots (
        id SERIAL PRIMARY KEY,
        year INTEGER NOT NULL UNIQUE,
        imported_at TIMESTAMPTZ DEFAULT NOW(),
        imported_by INTEGER,
        source_file TEXT,
        data TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS keeper_selections (
        id SERIAL PRIMARY KEY,
        year INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        current_contract TEXT NOT NULL,
        action TEXT NOT NULL,
        extension_years INTEGER DEFAULT 0,
        next_contract TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(year, team_id, player_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS keeper_submissions (
        id SERIAL PRIMARY KEY,
        year INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        submitted_at TIMESTAMPTZ DEFAULT NOW(),
        submitted_by INTEGER,
        selections TEXT NOT NULL,
        validation_result TEXT,
        is_valid INTEGER DEFAULT 0,
        commissioner_approved INTEGER DEFAULT 0,
        commissioner_notes TEXT,
        UNIQUE(year, team_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_log (
        id SERIAL PRIMARY KEY,
        year INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        notification_type TEXT NOT NULL,
        channel TEXT NOT NULL DEFAULT 'email',
        recipient_email TEXT,
        sent_at TIMESTAMPTZ DEFAULT NOW(),
        sent_by TEXT,
        status TEXT DEFAULT 'sent',
        error_message TEXT
    )
    """,
]


def get_db() -> psycopg2.extensions.connection:
    """Get a database connection with RealDictCursor."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def _fetchone(conn, query: str, params: tuple = ()) -> Optional[dict]:
    """Execute query and return one row as dict, or None."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetchall(conn, query: str, params: tuple = ()) -> list[dict]:
    """Execute query and return all rows as list of dicts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


async def init_db():
    """Initialize the database schema."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            for stmt in SCHEMA_STATEMENTS:
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def seed_if_empty():
    """Auto-seed 2026 contract data if DB has no league snapshots."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM league_snapshots")
            count = cur.fetchone()[0]
        if count > 0:
            print(f"[Seed] League data already present ({count} snapshots). Skipping.")
            return
    finally:
        conn.close()

    print("[Seed] No league data found. Loading 2026 contracts...")
    from scripts.load_2026_contracts import load_contracts
    load_contracts()
    print("[Seed] Contract data loaded successfully.")


# ========== Users ==========

def get_user_by_guid(yahoo_guid: str) -> Optional[dict]:
    conn = get_db()
    try:
        return _fetchone(conn, "SELECT * FROM users WHERE yahoo_guid = %s", (yahoo_guid,))
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        return _fetchone(conn, "SELECT * FROM users WHERE id = %s", (user_id,))
    finally:
        conn.close()


def upsert_user(
    yahoo_guid: str,
    yahoo_nickname: str = "",
    yahoo_email: str = "",
    team_id: Optional[int] = None,
    is_commissioner: bool = False,
) -> dict:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (yahoo_guid, yahoo_nickname, yahoo_email, team_id, is_commissioner, last_login)
                   VALUES (%s, %s, %s, %s, %s, NOW())
                   ON CONFLICT(yahoo_guid) DO UPDATE SET
                       yahoo_nickname = EXCLUDED.yahoo_nickname,
                       yahoo_email = COALESCE(EXCLUDED.yahoo_email, users.yahoo_email),
                       team_id = COALESCE(EXCLUDED.team_id, users.team_id),
                       last_login = NOW()""",
                (yahoo_guid, yahoo_nickname, yahoo_email, team_id, int(is_commissioner)),
            )
        conn.commit()
        return get_user_by_guid(yahoo_guid)
    finally:
        conn.close()


# ========== Teams ==========

def get_all_teams() -> list[dict]:
    conn = get_db()
    try:
        return _fetchall(conn, "SELECT * FROM teams ORDER BY id")
    finally:
        conn.close()


def get_team_by_id(team_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        return _fetchone(conn, "SELECT * FROM teams WHERE id = %s", (team_id,))
    finally:
        conn.close()


def get_team_by_manager(manager_name: str) -> Optional[dict]:
    conn = get_db()
    try:
        return _fetchone(
            conn, "SELECT * FROM teams WHERE manager_name = %s", (manager_name,)
        )
    finally:
        conn.close()


def upsert_team(manager_name: str, team_name: str = "", yahoo_team_id: str = "") -> dict:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO teams (manager_name, team_name, yahoo_team_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT(manager_name) DO UPDATE SET
                       team_name = COALESCE(NULLIF(EXCLUDED.team_name, ''), teams.team_name),
                       yahoo_team_id = COALESCE(NULLIF(EXCLUDED.yahoo_team_id, ''), teams.yahoo_team_id)""",
                (manager_name, team_name, yahoo_team_id),
            )
        conn.commit()
        return get_team_by_manager(manager_name)
    finally:
        conn.close()


def update_team_adjustments(team_id: int, trade_compensation: int, faab_adjustment: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE teams SET trade_compensation = %s, faab_adjustment = %s
                   WHERE id = %s""",
                (trade_compensation, faab_adjustment, team_id),
            )
        conn.commit()
    finally:
        conn.close()


# ========== League Snapshots ==========

def get_snapshot_years() -> list[int]:
    conn = get_db()
    try:
        rows = _fetchall(conn, "SELECT year FROM league_snapshots ORDER BY year")
        return [r["year"] for r in rows]
    finally:
        conn.close()


def get_snapshot(year: int) -> Optional[dict]:
    conn = get_db()
    try:
        result = _fetchone(
            conn, "SELECT * FROM league_snapshots WHERE year = %s", (year,)
        )
        if not result:
            return None
        result["data"] = json.loads(result["data"])
        return result
    finally:
        conn.close()


def save_snapshot(year: int, data: dict, source_file: str = "", imported_by: Optional[int] = None):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO league_snapshots (year, data, source_file, imported_by)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT(year) DO UPDATE SET
                       data = EXCLUDED.data,
                       source_file = EXCLUDED.source_file,
                       imported_by = EXCLUDED.imported_by,
                       imported_at = NOW()""",
                (year, json.dumps(data, ensure_ascii=False), source_file, imported_by),
            )
        conn.commit()
    finally:
        conn.close()


# ========== Keeper Selections ==========

def get_keeper_selections(year: int, team_id: int) -> list[dict]:
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT * FROM keeper_selections
               WHERE year = %s AND team_id = %s
               ORDER BY player_name""",
            (year, team_id),
        )
    finally:
        conn.close()


def upsert_keeper_selection(
    year: int,
    team_id: int,
    player_name: str,
    current_contract: str,
    action: str,
    extension_years: int = 0,
    next_contract: str = "",
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO keeper_selections
                   (year, team_id, player_name, current_contract, action, extension_years, next_contract)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT(year, team_id, player_name) DO UPDATE SET
                       current_contract = EXCLUDED.current_contract,
                       action = EXCLUDED.action,
                       extension_years = EXCLUDED.extension_years,
                       next_contract = EXCLUDED.next_contract,
                       updated_at = NOW()""",
                (year, team_id, player_name, current_contract, action, extension_years, next_contract),
            )
        conn.commit()
    finally:
        conn.close()


def delete_keeper_selections(year: int, team_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM keeper_selections WHERE year = %s AND team_id = %s",
                (year, team_id),
            )
        conn.commit()
    finally:
        conn.close()


# ========== Keeper Submissions ==========

def get_submission(year: int, team_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        result = _fetchone(
            conn,
            "SELECT * FROM keeper_submissions WHERE year = %s AND team_id = %s",
            (year, team_id),
        )
        if not result:
            return None
        result["selections"] = json.loads(result["selections"])
        if result["validation_result"]:
            result["validation_result"] = json.loads(result["validation_result"])
        return result
    finally:
        conn.close()


def get_all_submissions(year: int) -> list[dict]:
    conn = get_db()
    try:
        rows = _fetchall(
            conn,
            """SELECT ks.*, t.manager_name, t.team_name
               FROM keeper_submissions ks
               JOIN teams t ON ks.team_id = t.id
               WHERE ks.year = %s
               ORDER BY t.manager_name""",
            (year,),
        )
        for r in rows:
            r["selections"] = json.loads(r["selections"])
            if r["validation_result"]:
                r["validation_result"] = json.loads(r["validation_result"])
        return rows
    finally:
        conn.close()


def upsert_submission(
    year: int,
    team_id: int,
    submitted_by: Optional[int],
    selections: list[dict],
    validation_result: dict,
    is_valid: bool,
):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO keeper_submissions
                   (year, team_id, submitted_by, selections, validation_result, is_valid)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT(year, team_id) DO UPDATE SET
                       submitted_at = NOW(),
                       submitted_by = EXCLUDED.submitted_by,
                       selections = EXCLUDED.selections,
                       validation_result = EXCLUDED.validation_result,
                       is_valid = EXCLUDED.is_valid,
                       commissioner_approved = 0""",
                (
                    year, team_id, submitted_by,
                    json.dumps(selections, ensure_ascii=False),
                    json.dumps(validation_result, ensure_ascii=False),
                    int(is_valid),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def approve_submission(year: int, team_id: int, approved: bool, notes: str = ""):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE keeper_submissions
                   SET commissioner_approved = %s, commissioner_notes = %s
                   WHERE year = %s AND team_id = %s""",
                (int(approved), notes, year, team_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete_submission(year: int, team_id: int):
    """Delete a submission record (unlock). Keeper selections are preserved."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM keeper_submissions WHERE year = %s AND team_id = %s",
                (year, team_id),
            )
        conn.commit()
    finally:
        conn.close()


# ========== Notification Log ==========

def get_recent_notifications(
    year: int, team_id: int, notification_type: str, hours: int = 24
) -> list[dict]:
    """Check if a notification was sent recently (cooldown window)."""
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT * FROM notification_log
               WHERE year = %s AND team_id = %s
                 AND notification_type = %s
                 AND status = 'sent'
                 AND sent_at > NOW() - INTERVAL '%s hours'
               ORDER BY sent_at DESC""",
            (year, team_id, notification_type, hours),
        )
    finally:
        conn.close()


def insert_notification_log(
    year: int,
    team_id: int,
    notification_type: str,
    channel: str,
    recipient_email: str,
    sent_by: str,
    status: str,
    error_message: str = "",
):
    """Record a notification send attempt."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO notification_log
                   (year, team_id, notification_type, channel, recipient_email,
                    sent_by, status, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (year, team_id, notification_type, channel, recipient_email,
                 sent_by, status, error_message),
            )
        conn.commit()
    finally:
        conn.close()


def get_reminder_history(year: int) -> list[dict]:
    """Get all notification records for a year (for commissioner dashboard)."""
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT n.*, t.manager_name
               FROM notification_log n
               JOIN teams t ON n.team_id = t.id
               WHERE n.year = %s
               ORDER BY n.sent_at DESC
               LIMIT 100""",
            (year,),
        )
    finally:
        conn.close()
