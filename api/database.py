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
        line_name TEXT DEFAULT '',
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


# ========== Versioned Migration System ==========
# Each migration has a unique version key and a list of SQL statements.
# Migrations are tracked in `schema_migrations` table so each runs only once.
# All statements within a migration must be idempotent as a safety measure.

MIGRATIONS: dict[str, list[str]] = {
    "001_add_line_name": [
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'line_name'
            ) THEN
                ALTER TABLE users ADD COLUMN line_name TEXT DEFAULT '';
            END IF;
        END $$;
        """,
    ],
    "002_add_indexes": [
        "CREATE INDEX IF NOT EXISTS idx_users_team_id ON users(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_keeper_selections_year_team ON keeper_selections(year, team_id)",
        "CREATE INDEX IF NOT EXISTS idx_keeper_submissions_year_team ON keeper_submissions(year, team_id)",
        "CREATE INDEX IF NOT EXISTS idx_notification_log_team_year ON notification_log(team_id, year, notification_type)",
        "CREATE INDEX IF NOT EXISTS idx_notification_log_sent_at ON notification_log(sent_at DESC)",
    ],
    "004_buyouts_table": [
        """
        CREATE TABLE IF NOT EXISTS buyouts (
            id SERIAL PRIMARY KEY,
            team_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            original_contract TEXT NOT NULL,
            buyout_salary INTEGER NOT NULL,
            buyout_faab INTEGER DEFAULT 0,
            buyout_years INTEGER NOT NULL,
            remaining_years INTEGER NOT NULL,
            buyout_type TEXT NOT NULL DEFAULT 'keeper_release',
            use_faab BOOLEAN DEFAULT FALSE,
            notes TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_buyouts_team_year ON buyouts(team_id, year)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_buyouts_team_id'
            ) THEN
                ALTER TABLE buyouts
                    ADD CONSTRAINT fk_buyouts_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
    ],
    "003_add_foreign_keys": [
        # users.team_id -> teams.id (nullable, SET NULL on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_users_team_id'
            ) THEN
                -- Clean orphan references before adding FK
                UPDATE users SET team_id = NULL
                WHERE team_id IS NOT NULL
                  AND team_id NOT IN (SELECT id FROM teams);
                ALTER TABLE users
                    ADD CONSTRAINT fk_users_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
        # keeper_selections.team_id -> teams.id (required, CASCADE on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_keeper_selections_team_id'
            ) THEN
                DELETE FROM keeper_selections
                WHERE team_id NOT IN (SELECT id FROM teams);
                ALTER TABLE keeper_selections
                    ADD CONSTRAINT fk_keeper_selections_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        # keeper_submissions.team_id -> teams.id (required, CASCADE on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_keeper_submissions_team_id'
            ) THEN
                DELETE FROM keeper_submissions
                WHERE team_id NOT IN (SELECT id FROM teams);
                ALTER TABLE keeper_submissions
                    ADD CONSTRAINT fk_keeper_submissions_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        # keeper_submissions.submitted_by -> users.id (nullable, SET NULL on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_keeper_submissions_submitted_by'
            ) THEN
                UPDATE keeper_submissions SET submitted_by = NULL
                WHERE submitted_by IS NOT NULL
                  AND submitted_by NOT IN (SELECT id FROM users);
                ALTER TABLE keeper_submissions
                    ADD CONSTRAINT fk_keeper_submissions_submitted_by
                    FOREIGN KEY (submitted_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
        # notification_log.team_id -> teams.id (required, CASCADE on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_notification_log_team_id'
            ) THEN
                DELETE FROM notification_log
                WHERE team_id NOT IN (SELECT id FROM teams);
                ALTER TABLE notification_log
                    ADD CONSTRAINT fk_notification_log_team_id
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        # league_snapshots.imported_by -> users.id (nullable, SET NULL on delete)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_league_snapshots_imported_by'
            ) THEN
                UPDATE league_snapshots SET imported_by = NULL
                WHERE imported_by IS NOT NULL
                  AND imported_by NOT IN (SELECT id FROM users);
                ALTER TABLE league_snapshots
                    ADD CONSTRAINT fk_league_snapshots_imported_by
                    FOREIGN KEY (imported_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """,
    ],
    "005_yahoo_tokens": [
        """
        CREATE TABLE IF NOT EXISTS yahoo_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            token_type TEXT DEFAULT 'bearer',
            expires_at TIMESTAMPTZ,
            yahoo_guid TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id)
        )
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_yahoo_tokens_user_id'
            ) THEN
                ALTER TABLE yahoo_tokens
                    ADD CONSTRAINT fk_yahoo_tokens_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS idx_yahoo_tokens_user_id ON yahoo_tokens(user_id)",
    ],
    "006_player_rankings": [
        """
        CREATE TABLE IF NOT EXISTS player_rankings (
            id SERIAL PRIMARY KEY,
            year INTEGER NOT NULL,
            player_key TEXT NOT NULL,
            player_name TEXT NOT NULL,
            o_rank INTEGER,
            x_rank INTEGER,
            position TEXT DEFAULT '',
            mlb_team TEXT DEFAULT '',
            -- Hitting stats (previous season actual)
            stat_r INTEGER, stat_h INTEGER, stat_hr INTEGER,
            stat_rbi INTEGER, stat_sb INTEGER,
            stat_avg REAL, stat_ops REAL,
            -- Pitching stats (previous season actual)
            stat_w INTEGER, stat_sv INTEGER, stat_hld INTEGER,
            stat_k INTEGER, stat_era REAL, stat_whip REAL, stat_qs INTEGER,
            -- Projections (current season)
            proj_r INTEGER, proj_h INTEGER, proj_hr INTEGER,
            proj_rbi INTEGER, proj_sb INTEGER,
            proj_avg REAL, proj_ops REAL,
            proj_w INTEGER, proj_sv INTEGER, proj_hld INTEGER,
            proj_k INTEGER, proj_era REAL, proj_whip REAL, proj_qs INTEGER,
            -- Metadata
            fetched_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(year, player_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_player_rankings_year ON player_rankings(year)",
        "CREATE INDEX IF NOT EXISTS idx_player_rankings_year_orank ON player_rankings(year, o_rank)",
    ],
    "007_add_ar_rank": [
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'player_rankings' AND column_name = 'ar_rank'
            ) THEN
                ALTER TABLE player_rankings ADD COLUMN ar_rank INTEGER;
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS idx_player_rankings_year_arrank ON player_rankings(year, ar_rank)",
    ],
    "008_add_ab_ip_columns": [
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'player_rankings' AND column_name = 'stat_ab'
            ) THEN
                ALTER TABLE player_rankings
                    ADD COLUMN stat_ab INTEGER,
                    ADD COLUMN proj_ab INTEGER,
                    ADD COLUMN stat_ip REAL,
                    ADD COLUMN proj_ip REAL;
            END IF;
        END $$;
        """,
    ],
    "009_add_stats_sort_type": [
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'player_rankings' AND column_name = 'stats_sort_type'
            ) THEN
                ALTER TABLE player_rankings
                    ADD COLUMN stats_sort_type TEXT DEFAULT 'prev_season';
            END IF;
        END $$;
        """,
    ],
    "010_rookie_callup_log": [
        """
        CREATE TABLE IF NOT EXISTS rookie_callup_log (
            id SERIAL PRIMARY KEY,
            player_name TEXT NOT NULL,
            player_key TEXT,
            mlb_team TEXT,
            owner_manager TEXT,
            owner_team_id INTEGER,
            year INTEGER NOT NULL,
            callup_date DATE,
            detection_source TEXT DEFAULT 'mlb_api',
            notified BOOLEAN DEFAULT FALSE,
            notified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_rookie_callup_player_year ON rookie_callup_log(player_name, year)",
    ],
}


def _ensure_migration_table(conn):
    """Create the migration tracking table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    conn.commit()


def _get_applied_migrations(conn) -> set[str]:
    """Return set of already-applied migration versions."""
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return {row[0] for row in cur.fetchall()}


def _run_migrations(conn):
    """Run all pending migrations in order, tracking each in schema_migrations."""
    _ensure_migration_table(conn)
    applied = _get_applied_migrations(conn)

    for version in sorted(MIGRATIONS.keys()):
        if version in applied:
            continue
        statements = MIGRATIONS[version]
        print(f"[Migration] Applying {version} ...", flush=True)
        try:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            conn.commit()
            print(f"[Migration] {version} applied.", flush=True)
        except Exception as e:
            conn.rollback()
            print(f"[Migration] {version} FAILED: {e}", flush=True)
            raise


async def init_db():
    """Initialize the database schema and run versioned migrations."""
    conn = get_db()
    try:
        # 1) Create tables
        with conn.cursor() as cur:
            for stmt in SCHEMA_STATEMENTS:
                cur.execute(stmt)
        conn.commit()

        # 2) Run versioned migrations
        _run_migrations(conn)
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


def update_user_line_name(user_id: int, line_name: str):
    """Update user's LINE display name."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET line_name = %s WHERE id = %s",
                (line_name.strip(), user_id),
            )
        conn.commit()
    finally:
        conn.close()


# ========== Teams ==========

def get_all_teams() -> list[dict]:
    conn = get_db()
    try:
        return _fetchall(conn, "SELECT * FROM teams ORDER BY id")
    finally:
        conn.close()


def get_team_line_names() -> dict[int, str]:
    """Return mapping of team_id -> line_name from users table."""
    conn = get_db()
    try:
        rows = _fetchall(
            conn,
            """SELECT u.team_id, u.line_name
               FROM users u
               WHERE u.team_id IS NOT NULL AND u.line_name IS NOT NULL AND u.line_name != ''""",
        )
        return {r["team_id"]: r["line_name"] for r in rows}
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
                 AND sent_at > NOW() - make_interval(hours => %s)
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


# ========== Buyouts ==========

def get_team_buyouts(team_id: int, year: int) -> list[dict]:
    """Get all active buyout records for a team in a specific year."""
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT * FROM buyouts
               WHERE team_id = %s AND year <= %s AND remaining_years > 0
               ORDER BY player_name""",
            (team_id, year),
        )
    finally:
        conn.close()


def get_all_buyouts(year: int) -> list[dict]:
    """Get all buyout records for a year (commissioner view)."""
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT b.*, t.manager_name
               FROM buyouts b
               JOIN teams t ON b.team_id = t.id
               WHERE b.year <= %s AND b.remaining_years > 0
               ORDER BY t.manager_name, b.player_name""",
            (year,),
        )
    finally:
        conn.close()


def create_buyout(
    team_id: int,
    year: int,
    player_name: str,
    original_contract: str,
    buyout_salary: int,
    buyout_faab: int,
    buyout_years: int,
    remaining_years: int,
    buyout_type: str = "keeper_release",
    use_faab: bool = False,
    notes: str = "",
) -> dict:
    """Create a new buyout record."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO buyouts
                   (team_id, year, player_name, original_contract,
                    buyout_salary, buyout_faab, buyout_years, remaining_years,
                    buyout_type, use_faab, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (team_id, year, player_name, original_contract,
                 buyout_salary, buyout_faab, buyout_years, remaining_years,
                 buyout_type, use_faab, notes),
            )
            result = dict(cur.fetchone())
        conn.commit()
        return result
    finally:
        conn.close()


def update_buyout(buyout_id: int, **kwargs) -> dict:
    """Update a buyout record. Pass only the fields to update."""
    allowed = {
        "player_name", "original_contract", "buyout_salary", "buyout_faab",
        "buyout_years", "remaining_years", "buyout_type", "use_faab", "notes",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        conn = get_db()
        try:
            return _fetchone(conn, "SELECT * FROM buyouts WHERE id = %s", (buyout_id,))
        finally:
            conn.close()

    set_clauses = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [buyout_id]

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE buyouts SET {set_clauses} WHERE id = %s RETURNING *",
                values,
            )
            result = cur.fetchone()
        conn.commit()
        return dict(result) if result else None
    finally:
        conn.close()


def delete_buyout(buyout_id: int):
    """Delete a buyout record."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM buyouts WHERE id = %s", (buyout_id,))
        conn.commit()
    finally:
        conn.close()


# ========== Yahoo Tokens ==========

def get_yahoo_token(user_id: int) -> Optional[dict]:
    """Get Yahoo OAuth token for a specific user."""
    conn = get_db()
    try:
        return _fetchone(
            conn,
            "SELECT * FROM yahoo_tokens WHERE user_id = %s",
            (user_id,),
        )
    finally:
        conn.close()


def get_commissioner_yahoo_token() -> Optional[dict]:
    """Get the Yahoo token for a commissioner user (most recently updated)."""
    conn = get_db()
    try:
        return _fetchone(
            conn,
            """SELECT yt.* FROM yahoo_tokens yt
               JOIN users u ON u.id = yt.user_id
               WHERE u.is_commissioner = 1
               ORDER BY yt.updated_at DESC
               LIMIT 1""",
        )
    finally:
        conn.close()


def upsert_yahoo_token(
    user_id: int,
    access_token: str,
    refresh_token: str,
    expires_at=None,
    yahoo_guid: str = "",
    token_type: str = "bearer",
) -> Optional[dict]:
    """Insert or update Yahoo OAuth token for a user."""
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO yahoo_tokens
                       (user_id, access_token, refresh_token, token_type, expires_at, yahoo_guid)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT(user_id) DO UPDATE SET
                       access_token = EXCLUDED.access_token,
                       refresh_token = EXCLUDED.refresh_token,
                       token_type = EXCLUDED.token_type,
                       expires_at = EXCLUDED.expires_at,
                       yahoo_guid = EXCLUDED.yahoo_guid,
                       updated_at = NOW()
                   RETURNING *""",
                (user_id, access_token, refresh_token, token_type, expires_at, yahoo_guid),
            )
            result = cur.fetchone()
        conn.commit()
        return dict(result) if result else None
    finally:
        conn.close()


def delete_yahoo_token(user_id: int):
    """Remove a user's Yahoo OAuth token (disconnect)."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM yahoo_tokens WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ========== Player Rankings ==========

def get_player_rankings(year: int) -> list[dict]:
    """Get all player rankings for a year."""
    conn = get_db()
    try:
        return _fetchall(
            conn,
            """SELECT * FROM player_rankings
               WHERE year = %s
               ORDER BY COALESCE(o_rank, 9999)""",
            (year,),
        )
    finally:
        conn.close()


def bulk_upsert_player_rankings(year: int, players: list[dict]):
    """Bulk insert/update player rankings for a year.

    Each player dict should have keys matching column names:
    player_key, player_name, o_rank, ar_rank (optional), position, mlb_team,
    stat_* (actual stats), proj_* (projections).
    Note: x_rank column still exists in DB for backward compatibility but is no longer written.
    """
    if not players:
        return

    conn = get_db()
    try:
        with conn.cursor() as cur:
            for p in players:
                cur.execute(
                    """INSERT INTO player_rankings
                       (year, player_key, player_name, o_rank, ar_rank,
                        position, mlb_team,
                        stat_ab, stat_r, stat_h, stat_hr, stat_rbi, stat_sb, stat_avg, stat_ops,
                        stat_ip, stat_w, stat_sv, stat_hld, stat_k, stat_era, stat_whip, stat_qs,
                        proj_ab, proj_r, proj_h, proj_hr, proj_rbi, proj_sb, proj_avg, proj_ops,
                        proj_ip, proj_w, proj_sv, proj_hld, proj_k, proj_era, proj_whip, proj_qs,
                        fetched_at)
                       VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        NOW())
                       ON CONFLICT(year, player_key) DO UPDATE SET
                        player_name = EXCLUDED.player_name,
                        o_rank = EXCLUDED.o_rank,
                        ar_rank = EXCLUDED.ar_rank,
                        position = EXCLUDED.position,
                        mlb_team = EXCLUDED.mlb_team,
                        stat_ab = EXCLUDED.stat_ab,
                        stat_r = EXCLUDED.stat_r, stat_h = EXCLUDED.stat_h,
                        stat_hr = EXCLUDED.stat_hr, stat_rbi = EXCLUDED.stat_rbi,
                        stat_sb = EXCLUDED.stat_sb, stat_avg = EXCLUDED.stat_avg,
                        stat_ops = EXCLUDED.stat_ops,
                        stat_ip = EXCLUDED.stat_ip,
                        stat_w = EXCLUDED.stat_w, stat_sv = EXCLUDED.stat_sv,
                        stat_hld = EXCLUDED.stat_hld, stat_k = EXCLUDED.stat_k,
                        stat_era = EXCLUDED.stat_era, stat_whip = EXCLUDED.stat_whip,
                        stat_qs = EXCLUDED.stat_qs,
                        proj_ab = EXCLUDED.proj_ab,
                        proj_r = EXCLUDED.proj_r, proj_h = EXCLUDED.proj_h,
                        proj_hr = EXCLUDED.proj_hr, proj_rbi = EXCLUDED.proj_rbi,
                        proj_sb = EXCLUDED.proj_sb, proj_avg = EXCLUDED.proj_avg,
                        proj_ops = EXCLUDED.proj_ops,
                        proj_ip = EXCLUDED.proj_ip,
                        proj_w = EXCLUDED.proj_w, proj_sv = EXCLUDED.proj_sv,
                        proj_hld = EXCLUDED.proj_hld, proj_k = EXCLUDED.proj_k,
                        proj_era = EXCLUDED.proj_era, proj_whip = EXCLUDED.proj_whip,
                        proj_qs = EXCLUDED.proj_qs,
                        fetched_at = NOW()""",
                    (
                        year, p["player_key"], p["player_name"],
                        p.get("o_rank"), p.get("ar_rank"),
                        p.get("position", ""), p.get("mlb_team", ""),
                        # Hitting stats
                        p.get("stat_ab"), p.get("stat_r"), p.get("stat_h"),
                        p.get("stat_hr"), p.get("stat_rbi"), p.get("stat_sb"),
                        p.get("stat_avg"), p.get("stat_ops"),
                        # Pitching stats
                        p.get("stat_ip"), p.get("stat_w"), p.get("stat_sv"),
                        p.get("stat_hld"), p.get("stat_k"), p.get("stat_era"),
                        p.get("stat_whip"), p.get("stat_qs"),
                        # Projections hitting
                        p.get("proj_ab"), p.get("proj_r"), p.get("proj_h"),
                        p.get("proj_hr"), p.get("proj_rbi"), p.get("proj_sb"),
                        p.get("proj_avg"), p.get("proj_ops"),
                        # Projections pitching
                        p.get("proj_ip"), p.get("proj_w"), p.get("proj_sv"),
                        p.get("proj_hld"), p.get("proj_k"), p.get("proj_era"),
                        p.get("proj_whip"), p.get("proj_qs"),
                    ),
                )
        conn.commit()
        print(f"[PlayerRankings] Upserted {len(players)} rankings for year {year}", flush=True)
    finally:
        conn.close()


def update_last_season_stats(year: int, players: list[dict], sort_type: str = "prev_season"):
    """Update stat_* columns for existing players by matching player_name.

    Used to fill in previous/current season stats from Yahoo API.
    Matches by player_name (case-insensitive) against records already in
    the player_rankings table for the given year.

    Args:
        year: The target year in the player_rankings table
        players: list of dicts with player_name and stat_* columns
        sort_type: Which sort_type was used to fetch these stats
                   (e.g. "prev_season", "season", "lastweek", "lastmonth", "date")
    """
    if not players:
        return

    conn = get_db()
    try:
        updated = 0
        with conn.cursor() as cur:
            for p in players:
                name = p.get("player_name", "")
                if not name:
                    continue
                cur.execute(
                    """UPDATE player_rankings
                       SET stat_ab = %s, stat_r = %s, stat_h = %s, stat_hr = %s,
                           stat_rbi = %s, stat_sb = %s,
                           stat_avg = %s, stat_ops = %s,
                           stat_ip = %s, stat_w = %s, stat_sv = %s, stat_hld = %s,
                           stat_k = %s, stat_era = %s, stat_whip = %s,
                           stat_qs = %s,
                           stats_sort_type = %s,
                           fetched_at = NOW()
                       WHERE year = %s AND LOWER(player_name) = LOWER(%s)""",
                    (
                        p.get("stat_ab"), p.get("stat_r"), p.get("stat_h"),
                        p.get("stat_hr"), p.get("stat_rbi"), p.get("stat_sb"),
                        p.get("stat_avg"), p.get("stat_ops"),
                        p.get("stat_ip"), p.get("stat_w"), p.get("stat_sv"),
                        p.get("stat_hld"), p.get("stat_k"), p.get("stat_era"),
                        p.get("stat_whip"), p.get("stat_qs"),
                        sort_type,
                        year, name,
                    ),
                )
                if cur.rowcount > 0:
                    updated += 1
        conn.commit()
        print(
            f"[PlayerRankings] Updated last-season stats for {updated}/{len(players)} "
            f"players (year {year})",
            flush=True,
        )
    finally:
        conn.close()


def update_ar_ranks(year: int, ar_data: dict[str, int]):
    """Update AR (Actual Rank) for players in a given year.

    Args:
        year: The season year
        ar_data: dict mapping player_key -> ar_rank
    """
    if not ar_data:
        return

    conn = get_db()
    try:
        with conn.cursor() as cur:
            for player_key, ar_rank in ar_data.items():
                cur.execute(
                    """UPDATE player_rankings
                       SET ar_rank = %s
                       WHERE year = %s AND player_key = %s""",
                    (ar_rank, year, player_key),
                )
        conn.commit()
        print(f"[PlayerRankings] Updated {len(ar_data)} AR ranks for year {year}", flush=True)
    finally:
        conn.close()


def get_ranking_fetch_status(year: int) -> dict:
    """Get the last fetch time and count for player rankings of a year."""
    conn = get_db()
    try:
        row = _fetchone(
            conn,
            """SELECT COUNT(*) as total_count,
                      MAX(fetched_at) as last_fetched_at
               FROM player_rankings WHERE year = %s""",
            (year,),
        )
        if row and row["total_count"] > 0:
            # Get the stats_sort_type (same for all rows of a year)
            sort_row = _fetchone(
                conn,
                """SELECT stats_sort_type FROM player_rankings
                   WHERE year = %s AND stats_sort_type IS NOT NULL
                   LIMIT 1""",
                (year,),
            )
            return {
                "has_data": True,
                "total_count": row["total_count"],
                "last_fetched_at": row["last_fetched_at"].isoformat() if row["last_fetched_at"] else None,
                "stats_sort_type": sort_row["stats_sort_type"] if sort_row else "prev_season",
            }
        return {"has_data": False, "total_count": 0, "last_fetched_at": None, "stats_sort_type": None}
    finally:
        conn.close()


# ── Rookie Call-up Log ──────────────────────────────────────────


def get_notified_callups(year: int) -> set[str]:
    """Return set of player_names already notified for this year."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT player_name FROM rookie_callup_log WHERE year = %s AND notified = TRUE",
                (year,),
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def record_callup(
    player_name: str,
    year: int,
    *,
    player_key: str = "",
    mlb_team: str = "",
    owner_manager: str = "",
    owner_team_id: int = 0,
    callup_date: str | None = None,
    detection_source: str = "mlb_api",
) -> int:
    """Insert a rookie call-up record and return its id."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO rookie_callup_log
                   (player_name, player_key, mlb_team, owner_manager,
                    owner_team_id, year, callup_date, detection_source,
                    notified, notified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                   RETURNING id""",
                (player_name, player_key, mlb_team, owner_manager,
                 owner_team_id, year, callup_date, detection_source),
            )
            row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    finally:
        conn.close()


def cleanup_old_notifications(retention_days: int = 365):
    """Delete notification_log records older than retention_days.
    Called on startup to prevent unbounded table growth."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM notification_log
                   WHERE sent_at < NOW() - make_interval(days => %s)""",
                (retention_days,),
            )
            deleted = cur.rowcount
        conn.commit()
        if deleted > 0:
            print(f"[Cleanup] Deleted {deleted} notification records older than {retention_days} days.")
    except Exception as e:
        conn.rollback()
        print(f"[Cleanup] notification_log cleanup failed (non-fatal): {e}")
    finally:
        conn.close()
