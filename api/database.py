"""
Fantasy Baseball Keeper League - SQLite Database Setup
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "keeper_league.db"),
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    yahoo_guid TEXT UNIQUE NOT NULL,
    yahoo_nickname TEXT,
    yahoo_email TEXT,
    team_id INTEGER REFERENCES teams(id),
    is_commissioner INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_name TEXT NOT NULL,
    team_name TEXT,
    yahoo_team_id TEXT,
    UNIQUE(manager_name)
);

CREATE TABLE IF NOT EXISTS league_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL UNIQUE,
    imported_at TEXT DEFAULT (datetime('now')),
    imported_by INTEGER REFERENCES users(id),
    source_file TEXT,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keeper_selections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    player_name TEXT NOT NULL,
    current_contract TEXT NOT NULL,
    action TEXT NOT NULL,
    extension_years INTEGER DEFAULT 0,
    next_contract TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(year, team_id, player_name)
);

CREATE TABLE IF NOT EXISTS keeper_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    submitted_at TEXT DEFAULT (datetime('now')),
    submitted_by INTEGER REFERENCES users(id),
    selections TEXT NOT NULL,
    validation_result TEXT,
    is_valid INTEGER DEFAULT 0,
    commissioner_approved INTEGER DEFAULT 0,
    commissioner_notes TEXT,
    UNIQUE(year, team_id)
);
"""


def get_db() -> sqlite3.Connection:
    """Get a synchronous database connection."""
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db():
    """Initialize the database schema."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# ========== Users ==========

def get_user_by_guid(yahoo_guid: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE yahoo_guid = ?", (yahoo_guid,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
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
        conn.execute(
            """INSERT INTO users (yahoo_guid, yahoo_nickname, yahoo_email, team_id, is_commissioner, last_login)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(yahoo_guid) DO UPDATE SET
                   yahoo_nickname = excluded.yahoo_nickname,
                   yahoo_email = COALESCE(excluded.yahoo_email, yahoo_email),
                   team_id = COALESCE(excluded.team_id, team_id),
                   last_login = datetime('now')""",
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
        rows = conn.execute("SELECT * FROM teams ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_team_by_id(team_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_team_by_manager(manager_name: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM teams WHERE manager_name = ?", (manager_name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_team(manager_name: str, team_name: str = "", yahoo_team_id: str = "") -> dict:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO teams (manager_name, team_name, yahoo_team_id)
               VALUES (?, ?, ?)
               ON CONFLICT(manager_name) DO UPDATE SET
                   team_name = COALESCE(NULLIF(excluded.team_name, ''), team_name),
                   yahoo_team_id = COALESCE(NULLIF(excluded.yahoo_team_id, ''), yahoo_team_id)""",
            (manager_name, team_name, yahoo_team_id),
        )
        conn.commit()
        return get_team_by_manager(manager_name)
    finally:
        conn.close()


# ========== League Snapshots ==========

def get_snapshot_years() -> list[int]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT year FROM league_snapshots ORDER BY year"
        ).fetchall()
        return [r["year"] for r in rows]
    finally:
        conn.close()


def get_snapshot(year: int) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM league_snapshots WHERE year = ?", (year,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["data"] = json.loads(result["data"])
        return result
    finally:
        conn.close()


def save_snapshot(year: int, data: dict, source_file: str = "", imported_by: Optional[int] = None):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO league_snapshots (year, data, source_file, imported_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(year) DO UPDATE SET
                   data = excluded.data,
                   source_file = excluded.source_file,
                   imported_by = excluded.imported_by,
                   imported_at = datetime('now')""",
            (year, json.dumps(data, ensure_ascii=False), source_file, imported_by),
        )
        conn.commit()
    finally:
        conn.close()


# ========== Keeper Selections ==========

def get_keeper_selections(year: int, team_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM keeper_selections
               WHERE year = ? AND team_id = ?
               ORDER BY player_name""",
            (year, team_id),
        ).fetchall()
        return [dict(r) for r in rows]
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
        conn.execute(
            """INSERT INTO keeper_selections
               (year, team_id, player_name, current_contract, action, extension_years, next_contract)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(year, team_id, player_name) DO UPDATE SET
                   current_contract = excluded.current_contract,
                   action = excluded.action,
                   extension_years = excluded.extension_years,
                   next_contract = excluded.next_contract,
                   updated_at = datetime('now')""",
            (year, team_id, player_name, current_contract, action, extension_years, next_contract),
        )
        conn.commit()
    finally:
        conn.close()


def delete_keeper_selections(year: int, team_id: int):
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM keeper_selections WHERE year = ? AND team_id = ?",
            (year, team_id),
        )
        conn.commit()
    finally:
        conn.close()


# ========== Keeper Submissions ==========

def get_submission(year: int, team_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM keeper_submissions WHERE year = ? AND team_id = ?",
            (year, team_id),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["selections"] = json.loads(result["selections"])
        if result["validation_result"]:
            result["validation_result"] = json.loads(result["validation_result"])
        return result
    finally:
        conn.close()


def get_all_submissions(year: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT ks.*, t.manager_name, t.team_name
               FROM keeper_submissions ks
               JOIN teams t ON ks.team_id = t.id
               WHERE ks.year = ?
               ORDER BY t.manager_name""",
            (year,),
        ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["selections"] = json.loads(r["selections"])
            if r["validation_result"]:
                r["validation_result"] = json.loads(r["validation_result"])
            results.append(r)
        return results
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
        conn.execute(
            """INSERT INTO keeper_submissions
               (year, team_id, submitted_by, selections, validation_result, is_valid)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(year, team_id) DO UPDATE SET
                   submitted_at = datetime('now'),
                   submitted_by = excluded.submitted_by,
                   selections = excluded.selections,
                   validation_result = excluded.validation_result,
                   is_valid = excluded.is_valid,
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
        conn.execute(
            """UPDATE keeper_submissions
               SET commissioner_approved = ?, commissioner_notes = ?
               WHERE year = ? AND team_id = ?""",
            (int(approved), notes, year, team_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_submission(year: int, team_id: int):
    """Delete a submission record (unlock). Keeper selections are preserved."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM keeper_submissions WHERE year = ? AND team_id = ?",
            (year, team_id),
        )
        conn.commit()
    finally:
        conn.close()
