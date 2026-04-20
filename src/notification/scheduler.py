"""
APScheduler-based background scheduler.

Jobs:
1. Keeper reminder: LINE group reminders every N days during keeper period.
2. Rookie call-up monitor: daily check for R-contract player MLB debuts.
3. Daily AR-Rank + season stats refresh: single-pass at 18:00 during MLB season.
4. Daily player status update: IL/DTD/NA/O status during MLB season.
5. Daily transaction fetch: Yahoo transactions during MLB season.
6. Daily roster + snapshot rebuild (with owner_manager sync): 00:30 Taiwan time.
7. Weekly war report: Monday 21:00 during MLB season.
8. Monthly war report: 1st of each month 20:45 during MLB season.

Yearly auto-mode: set REMINDER_MONTH / REMINDER_START_DAY / REMINDER_END_DAY
to define a fixed annual window (e.g. March 1-15 every year).
"""
from __future__ import annotations

import os
from datetime import datetime

# --- New: fixed annual window (preferred) ---
REMINDER_MONTH = int(os.getenv("REMINDER_MONTH", "3"))          # default March
REMINDER_START_DAY = int(os.getenv("REMINDER_START_DAY", "1"))   # default 1st
REMINDER_END_DAY = int(os.getenv("REMINDER_END_DAY", "15"))      # default 15th

# --- Legacy: explicit date range (overrides annual window if set) ---
KEEPER_REMINDER_START = os.getenv("KEEPER_REMINDER_START", "")
KEEPER_REMINDER_END = os.getenv("KEEPER_REMINDER_END", "")

REMINDER_CRON_HOUR = int(os.getenv("REMINDER_CRON_HOUR", "12"))
REMINDER_CRON_TZ = os.getenv("REMINDER_CRON_TZ", "Asia/Taipei")
REMINDER_INTERVAL_DAYS = int(os.getenv("REMINDER_INTERVAL_DAYS", "3"))

# --- Rookie call-up monitoring ---
# Active during MLB season (April-September by default)
ROOKIE_MONITOR_ENABLED = os.getenv("ROOKIE_MONITOR_ENABLED", "true").lower() == "true"
ROOKIE_MONITOR_START_MONTH = int(os.getenv("ROOKIE_MONITOR_START_MONTH", "3"))
ROOKIE_MONITOR_END_MONTH = int(os.getenv("ROOKIE_MONITOR_END_MONTH", "9"))

# --- Daily roster sync ---
DAILY_SYNC_HOUR = int(os.getenv("DAILY_SYNC_HOUR", "0"))           # midnight Taiwan time

# --- Injury notification batching ---
# Batch every N days so we don't spam LINE daily with tiny status changes.
INJURY_BATCH_DAYS = int(os.getenv("INJURY_BATCH_DAYS", "3"))

_scheduler = None


def _is_in_reminder_period(today: datetime) -> tuple[bool, str]:
    """Check if today falls within the reminder period.

    Returns (is_active, reason_if_inactive).

    Priority: if KEEPER_REMINDER_START is set, use explicit date range (legacy).
    Otherwise, use the fixed annual window (REMINDER_MONTH / START_DAY / END_DAY).
    """
    today_str = today.strftime("%Y-%m-%d")

    # Legacy mode: explicit date strings
    if KEEPER_REMINDER_START:
        if today_str < KEEPER_REMINDER_START:
            return False, f"Not yet in reminder period (start: {KEEPER_REMINDER_START})"
        if KEEPER_REMINDER_END and today_str > KEEPER_REMINDER_END:
            return False, f"Past reminder period (end: {KEEPER_REMINDER_END})"
        return True, ""

    # Annual window mode: fixed month/day range every year
    if today.month != REMINDER_MONTH:
        return False, f"Not in reminder month (current: {today.month}, target: {REMINDER_MONTH})"
    if today.day < REMINDER_START_DAY:
        return False, f"Before reminder start day (current: {today.day}, start: {REMINDER_START_DAY})"
    if today.day > REMINDER_END_DAY:
        return False, f"Past reminder end day (current: {today.day}, end: {REMINDER_END_DAY})"
    return True, ""


def _daily_reminder_job():
    """Daily job: send reminders if within the configured period."""
    now = datetime.now()
    active, reason = _is_in_reminder_period(now)

    if not active:
        print(f"[Scheduler] {reason}")
        return

    year = now.year
    # Cooldown = interval_days * 24 - 1 hour margin to avoid timezone drift
    cooldown = max(REMINDER_INTERVAL_DAYS * 24 - 1, 23)
    print(f"[Scheduler] Running keeper reminder check for year {year} "
          f"(interval: every {REMINDER_INTERVAL_DAYS} days, cooldown: {cooldown}h)...")

    try:
        from src.notification.reminder import send_reminders
        result = send_reminders(year, sent_by="scheduler", cooldown_hours=cooldown)
        pending_count = len(result["pending_managers"])
        if result["sent_to_group"]:
            print(f"[Scheduler] LINE group reminder sent. "
                  f"Pending teams: {pending_count} "
                  f"({', '.join(result['pending_managers'])})")
        elif result["skipped_reason"] == "all_submitted":
            print("[Scheduler] All teams submitted, no reminder needed.")
        elif result["skipped_reason"] == "cooldown":
            print(f"[Scheduler] Skipped (cooldown). Pending: {pending_count}")
        else:
            print(f"[Scheduler] Failed: {result['error']}")
    except Exception as e:
        print(f"[Scheduler] Error: {e}")


def _daily_rookie_monitor_job():
    """Daily job: check R-contract players for MLB call-ups."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season
    if month < ROOKIE_MONITOR_START_MONTH or month > ROOKIE_MONITOR_END_MONTH:
        print(f"[RookieScheduler] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[RookieScheduler] Checking R-contract call-ups for {year}...")

    try:
        from src.notification.rookie_monitor import send_callup_notifications
        result = send_callup_notifications(year)

        if result["new_callups"] > 0:
            status = "NOTIFIED" if result["notified"] else "DETECTED (notify failed)"
            print(f"[RookieScheduler] {status}: {result['new_callups']} new call-ups "
                  f"({', '.join(result['players'])})")
        else:
            print("[RookieScheduler] No new call-ups detected.")
    except Exception as e:
        print(f"[RookieScheduler] Error: {e}")


def _daily_ar_rank_refresh_job():
    """Daily job: refresh Yahoo AR (Actual Rank) + season stats in a single pass.

    Runs at 18:00 Taiwan time (= 6 AM ET) — after all US games end and Yahoo
    finishes processing stats from the previous day.

    Single pass: sort=AR + out=stats returns AR-sorted players WITH stats in one
    request stream, so we only fetch the top 1500 once (60 calls total).
    O-Rank is pre-season projection and rarely changes — fetch manually via Commissioner.
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[DailyRankStats] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[DailyRankStats] Starting AR-Rank + season stats refresh for {year}...")

    try:
        from api.yahoo_service import YahooTokenError
        from api.database import update_ar_ranks, update_last_season_stats
        from api.routers.commissioner import _fetch_yahoo_players_batch
        from config.settings import get_league_key

        league_key = get_league_key(year)
        if not league_key:
            print(f"[DailyRankStats] No league key for year {year}")
            return

        # One pass: AR-sorted players + season stats (out=stats via batch helper).
        players, errors = _fetch_yahoo_players_batch(
            league_key, sort="AR", sort_type="season",
            max_players=1500, stat_prefix="stat",
        )

        if not players:
            print("[DailyRankStats] No players fetched.")
            if errors:
                print(f"[DailyRankStats] Errors: {errors[:3]}")
            return

        ar_rank_map = {
            p["player_key"]: p["_rank"]
            for p in players
            if p.get("player_key") and p.get("_rank")
        }
        if ar_rank_map:
            update_ar_ranks(year, ar_rank_map)
            print(f"[DailyRankStats] Updated {len(ar_rank_map)} AR rankings")

        update_last_season_stats(year, players, sort_type="season")
        print(f"[DailyRankStats] Updated season stats for {len(players)} players")

        if errors:
            print(f"[DailyRankStats] Partial errors: {errors[:3]}")

        print(f"[DailyRankStats] Refresh complete for {year}")

    except YahooTokenError as e:
        print(f"[DailyRankStats] Token error: {e}")
    except Exception as e:
        print(f"[DailyRankStats] Error: {e}")


def _daily_player_status_job():
    """Daily job: update player IL/DTD/NA/O status from Yahoo API.
    Also detects status changes and sends LINE notifications for owned players."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[StatusUpdate] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[StatusUpdate] Updating player statuses for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_db
        import time

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[StatusUpdate] No league key for year {year}")
            return

        # Step 1: Fetch and update statuses from Yahoo (top 500 by overall rank)
        from api.routers.commissioner import _parse_yahoo_player
        updated = 0
        for start in range(0, 500, 25):
            try:
                path = (
                    f"/league/{league_key}/players"
                    f";start={start};count=25;sort=OR"
                    f";sort_type=season;out=stats"
                )
                data = yahoo_api_get(path)
                league_data = data.get("fantasy_content", {}).get("league", [])
                if len(league_data) < 2:
                    break

                players_section = league_data[1].get("players", {})
                count = players_section.get("count", 0)
                if count == 0:
                    break

                # Update status in DB
                conn = get_db()
                try:
                    cur = conn.cursor()
                    for key, val in players_section.items():
                        if key == "count":
                            continue
                        if isinstance(val, dict) and "player" in val:
                            pdata = val["player"]
                            if isinstance(pdata, list) and len(pdata) >= 1:
                                player_info = _parse_yahoo_player(pdata[0])
                                pk = player_info.get("player_key")
                                status = player_info.get("status")
                                if pk:
                                    cur.execute(
                                        "UPDATE player_rankings SET status = %s "
                                        "WHERE year = %s AND player_key = %s",
                                        (status, year, pk),
                                    )
                                    updated += 1
                    conn.commit()
                    cur.close()
                finally:
                    conn.close()
                time.sleep(1)

            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[StatusUpdate] Batch error at {start}: {e}")
                    break

        print(f"[StatusUpdate] Updated {updated} player statuses for {year}")

        # Step 2: Batched injury notification (every INJURY_BATCH_DAYS days).
        # DB updates happen daily for UI freshness, but LINE digest only every N days.
        from api.database import get_injury_baseline, save_injury_baseline, get_player_statuses

        baseline, last_checked_at = get_injury_baseline(year)
        current_statuses = get_player_statuses(year)

        if baseline is None:
            # First run: seed baseline, don't send.
            save_injury_baseline(year, current_statuses)
            print("[StatusUpdate] Injury baseline seeded, will notify on next cycle.")
            return

        # Cooldown check
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        # last_checked_at from psycopg2 is tz-aware UTC
        days_since = (now - last_checked_at).total_seconds() / 86400 if last_checked_at else 999
        if days_since < INJURY_BATCH_DAYS:
            print(f"[StatusUpdate] {days_since:.1f}d since last injury digest "
                  f"(<{INJURY_BATCH_DAYS}d), skipping LINE send.")
            return

        sent_or_empty = _send_injury_change_notification(year, baseline, current_statuses)
        if sent_or_empty:
            # Only advance baseline on successful send OR when there was nothing to send;
            # LINE API failures keep the baseline so we retry next day.
            save_injury_baseline(year, current_statuses)

    except Exception as e:
        print(f"[StatusUpdate] Error: {e}")


def _send_injury_change_notification(
    year: int,
    old_statuses: dict[str, dict],
    new_statuses: dict[str, dict],
) -> bool:
    """Compare old vs new statuses; send LINE digest. Return True on success/no-op, False on LINE failure."""
    from src.notification.line_service import send_line_group_message

    # Categorize changes (only for owned players)
    new_injuries: list[str] = []      # NULL/empty -> IL/DTD/IL-LT
    recovered: list[str] = []          # IL/DTD -> NULL/empty
    status_changes: list[str] = []     # IL -> DTD, DTD -> IL, etc.

    injury_statuses = {"IL", "IL-LT", "DTD", "NA", "O", "SUSP"}

    for pk, new_info in new_statuses.items():
        owner = new_info.get("owner_manager", "")
        if not owner:
            continue  # Skip FA players

        old_info = old_statuses.get(pk, {})
        old_status = old_info.get("status", "")
        new_status = new_info.get("status", "")

        if old_status == new_status:
            continue  # No change

        name = new_info["player_name"]
        pos = new_info.get("position", "")
        team = new_info.get("mlb_team", "")
        label = f"  {name} ({pos}/{team}) - {owner}" if pos else f"  {name} - {owner}"

        if (not old_status or old_status not in injury_statuses) and new_status in injury_statuses:
            new_injuries.append(f"{label} -> {new_status}")
        elif old_status in injury_statuses and (not new_status or new_status not in injury_statuses):
            recovered.append(f"{label} -> Active")
        elif old_status in injury_statuses and new_status in injury_statuses and old_status != new_status:
            status_changes.append(f"{label} -> {new_status} (was {old_status})")

    # No changes in the batch window — treat as success so baseline advances.
    if not new_injuries and not recovered and not status_changes:
        print("[StatusUpdate] No injury status changes in batch window.")
        return True

    header = f"[5-Man Keeper League] 傷兵異動彙整（近 {INJURY_BATCH_DAYS} 天）"
    lines = [header, ""]

    if new_injuries:
        lines.append("進入傷兵/異常名單:")
        lines.extend(new_injuries)
        lines.append("")

    if recovered:
        lines.append("解除傷兵名單:")
        lines.extend(recovered)
        lines.append("")

    if status_changes:
        lines.append("狀態變更:")
        lines.extend(status_changes)
        lines.append("")

    total = len(new_injuries) + len(recovered) + len(status_changes)
    message = "\n".join(lines)

    success, error = send_line_group_message(message)
    if success:
        print(f"[StatusUpdate] LINE injury digest sent ({total} changes).")
        return True
    print(f"[StatusUpdate] LINE notification failed: {error}")
    return False


def _daily_transaction_fetch_job():
    """Daily job: fetch latest transactions from Yahoo API during MLB season."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[TransactionFetch] Off-season (month {month}), skipping.")
        return

    year = now.year
    print(f"[TransactionFetch] Fetching transactions for {year}...")

    try:
        from api.yahoo_service import fetch_transactions_full, YahooTokenError
        import json
        from pathlib import Path

        # Resolve league key
        from config.settings import get_league_key
        league_key = get_league_key(year)
        if not league_key:
            print(f"[TransactionFetch] No league key for year {year}")
            return

        result = fetch_transactions_full(league_key)
        new_transactions = result.get("transactions", [])

        if not new_transactions:
            print("[TransactionFetch] No transactions found.")
            return

        # Load existing file and merge (dedup by transaction_id)
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tx_file = data_dir / f"yahoo_{year}_transactions.json"

        existing_tx = []
        if tx_file.exists():
            with open(tx_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            if isinstance(existing_data, dict):
                existing_tx = existing_data.get("transactions", [])
            elif isinstance(existing_data, list):
                existing_tx = existing_data

        # Dedup by transaction_id
        existing_ids = {tx.get("transaction_id") for tx in existing_tx}
        added = 0
        for tx in new_transactions:
            if tx.get("transaction_id") not in existing_ids:
                existing_tx.append(tx)
                added += 1

        # Save merged data
        save_data = {"transactions": existing_tx}
        with open(tx_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

        print(f"[TransactionFetch] {len(new_transactions)} total, "
              f"{added} new transactions added. "
              f"File: {tx_file.name} ({len(existing_tx)} total)")

    except Exception as e:
        print(f"[TransactionFetch] Error: {e}")


def sync_rosters_and_rebuild(year: int) -> dict:
    """Fetch full Yahoo rosters and rebuild next-year snapshot.

    Can be called from scheduler or commissioner API endpoint.

    Args:
        year: The current season year (e.g. 2026)

    Returns:
        dict with message, teams count, players count
    """
    print(f"[SnapshotRebuild] Fetching Yahoo {year} rosters...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_all_teams
        from config.settings import get_league_key
        import json as json_mod
        import time
        from pathlib import Path

        league_key = get_league_key(year)
        if not league_key:
            raise RuntimeError(f"No league key configured for year {year}")

        print(f"[SnapshotRebuild] League key: {league_key}")
        db_teams = get_all_teams()

        # Fetch teams list from Yahoo
        teams_path = f"/league/{league_key}/teams"
        print(f"[SnapshotRebuild] Fetching teams from: {teams_path}")
        teams_data = yahoo_api_get(teams_path)
        league_section = teams_data.get("fantasy_content", {}).get("league", [])
        if len(league_section) < 2:
            raise RuntimeError(
                f"Yahoo API returned no teams data. Response keys: "
                f"{list(teams_data.get('fantasy_content', {}).keys())}"
            )

        teams_section = league_section[1].get("teams", {})
        team_count = teams_section.get("count", 0)
        print(f"[SnapshotRebuild] Found {team_count} teams from Yahoo API")

        if team_count == 0:
            raise RuntimeError("Yahoo API returned 0 teams. Check league key or API status.")

        # Map yahoo_team_id -> manager_name from DB (multiple key formats)
        yahoo_id_to_manager: dict[str, str] = {}
        for db_team in db_teams:
            ytid = db_team.get("yahoo_team_id")
            if ytid:
                ytid_str = str(ytid)
                yahoo_id_to_manager[ytid_str] = db_team["manager_name"]
                # Also index by just the team number (e.g. "1" from "469.l.80910.t.1")
                if "." in ytid_str:
                    yahoo_id_to_manager[ytid_str.split(".")[-1]] = db_team["manager_name"]

        print(f"[SnapshotRebuild] DB team mappings: {yahoo_id_to_manager}")

        # Build full rosters dict: team_key -> {manager, team_name, players[]}
        all_rosters: dict[str, dict] = {}
        # Track player_key -> manager_name for owner_manager sync (replaces
        # the separate _daily_roster_ownership_sync_job that used to re-fetch
        # the same 16 rosters an hour earlier).
        ownership_map: dict[str, str] = {}
        total_players = 0
        skipped_teams: list[str] = []
        debug_logs: list[str] = []

        for i in range(team_count):
            team_entry = teams_section.get(str(i), {}).get("team", [])
            if not team_entry:
                skipped_teams.append(f"team_{i}: no entry")
                continue

            # Extract team info
            team_info_list = team_entry[0] if isinstance(team_entry, list) else []
            team_key = ""
            team_name = ""
            manager_name = ""

            for item in team_info_list:
                if isinstance(item, dict):
                    if "team_key" in item:
                        team_key = item["team_key"]
                    if "name" in item:
                        team_name = item["name"]

            # Resolve manager name from DB mapping (try full key, then number only)
            team_num = team_key.split(".")[-1] if team_key else ""
            manager_name = (
                yahoo_id_to_manager.get(team_key, "")
                or yahoo_id_to_manager.get(team_num, "")
            )
            if not manager_name:
                # Fallback: try from Yahoo managers field
                managers_list = next(
                    (item["managers"] for item in team_info_list
                     if isinstance(item, dict) and "managers" in item),
                    []
                )
                if managers_list and isinstance(managers_list, list):
                    mgr = managers_list[0].get("manager", {})
                    manager_name = mgr.get("nickname", "")

            if not team_key or not manager_name:
                skipped_teams.append(
                    f"team_{i}: key={team_key!r} name={team_name!r} manager={manager_name!r}"
                )
                print(f"[SnapshotRebuild] SKIPPING team_{i}: "
                      f"key={team_key!r} manager={manager_name!r}")
                continue

            # Fetch this team's full roster (with retry on 429)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    roster_path = f"/team/{team_key}/roster"
                    roster_data = yahoo_api_get(roster_path)
                    roster_section = (
                        roster_data.get("fantasy_content", {}).get("team", [])
                    )

                    # Debug: log structure of first team's response
                    if i == 0:
                        import json as _dbg_json
                        dbg = f"roster_section type={type(roster_section).__name__}, len={len(roster_section) if isinstance(roster_section, (list, dict)) else '?'}"
                        debug_logs.append(dbg)
                        print(f"[SnapshotRebuild] DEBUG {dbg}")
                        if isinstance(roster_section, list) and len(roster_section) >= 2:
                            rs1 = roster_section[1]
                            dbg2 = f"rs[1] keys={list(rs1.keys()) if isinstance(rs1, dict) else type(rs1).__name__}"
                            debug_logs.append(dbg2)
                            if isinstance(rs1, dict) and "roster" in rs1:
                                ri = rs1["roster"]
                                dbg3 = f"roster keys={list(ri.keys()) if isinstance(ri, dict) else type(ri).__name__}"
                                debug_logs.append(dbg3)
                                if isinstance(ri, dict) and "players" in ri:
                                    ps = ri["players"]
                                    dbg4 = f"players keys={list(ps.keys())[:5] if isinstance(ps, dict) else type(ps).__name__}, count={ps.get('count','?') if isinstance(ps, dict) else '?'}"
                                    debug_logs.append(dbg4)
                            else:
                                snippet = _dbg_json.dumps(rs1, ensure_ascii=False)[:400]
                                debug_logs.append(f"rs[1]={snippet}")
                        else:
                            snippet = _dbg_json.dumps(roster_section, ensure_ascii=False)[:400]
                            debug_logs.append(f"full={snippet}")

                    players: list[dict] = []
                    if len(roster_section) >= 2:
                        # Yahoo API structure: roster["0"]["players"]["0"]["player"]
                        roster_dict = roster_section[1].get("roster", {})
                        players_section = roster_dict.get("0", {}).get("players", {})
                        p_count = players_section.get("count", 0)
                        for j in range(p_count):
                            player_entry = players_section.get(str(j), {}).get("player", [])
                            if not player_entry:
                                continue
                            # Parse full player data (reuse yahoo_client pattern)
                            info_list = player_entry[0] if isinstance(player_entry, list) else []
                            p = {
                                "name": "", "player_key": "", "position": "",
                                "team": "", "selected_position": "", "status": "",
                            }
                            for item in info_list:
                                if isinstance(item, dict):
                                    if "name" in item:
                                        p["name"] = item["name"].get("full", "")
                                    if "player_key" in item:
                                        p["player_key"] = item["player_key"]
                                    if "display_position" in item:
                                        p["position"] = item["display_position"]
                                    if "editorial_team_abbr" in item:
                                        p["team"] = item["editorial_team_abbr"]
                                    if "status" in item:
                                        p["status"] = item["status"]
                            # Selected position
                            if len(player_entry) > 1 and isinstance(player_entry[1], dict):
                                sp_data = player_entry[1].get("selected_position", [])
                                if isinstance(sp_data, list):
                                    for s in sp_data:
                                        if isinstance(s, dict) and "position" in s:
                                            p["selected_position"] = s["position"]
                            if p["name"]:
                                players.append(p)
                                if p.get("player_key") and manager_name:
                                    ownership_map[p["player_key"]] = manager_name

                    all_rosters[team_key] = {
                        "manager": manager_name,
                        "team_name": team_name,
                        "players": players,
                    }
                    total_players += len(players)
                    print(
                        f"[SnapshotRebuild] {manager_name}: {len(players)} players "
                        f"({len(all_rosters)}/{team_count} teams done)"
                    )
                    time.sleep(1.0)
                    break  # success, exit retry loop

                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait_secs = 15 * (attempt + 1)
                        print(f"[SnapshotRebuild] 429 rate limit for {manager_name}, "
                              f"waiting {wait_secs}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_secs)
                    else:
                        print(f"[SnapshotRebuild] Error fetching {team_key} ({manager_name}): {e}")
                        break

        # Validate: require ALL teams with players before saving
        teams_with_players = sum(1 for t in all_rosters.values() if len(t.get("players", [])) > 0)
        if teams_with_players < 16:
            # Build diagnostic details
            empty_teams = [
                f"{t['manager']}({tk}): {len(t.get('players', []))}p"
                for tk, t in all_rosters.items()
                if len(t.get("players", [])) == 0
            ]
            diag = (
                f"teams_in_api={team_count}, "
                f"teams_matched={len(all_rosters)}, "
                f"teams_with_players={teams_with_players}, "
                f"debug={debug_logs}, "
                f"skipped={skipped_teams}, "
                f"empty={empty_teams}"
            )
            msg = (f"Only {teams_with_players}/{team_count} teams have player data. "
                   f"Aborting to prevent data loss. Diagnostic: {diag}")
            print(f"[SnapshotRebuild] {msg}")
            raise RuntimeError(msg)

        # Save to yahoo_{year}_rosters.json (local file)
        data_dir = Path(__file__).resolve().parents[2] / "data"
        rosters_path = data_dir / f"yahoo_{year}_rosters.json"
        rosters_path.write_text(
            json_mod.dumps(all_rosters, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"[SnapshotRebuild] Saved {rosters_path.name}: "
            f"{len(all_rosters)} teams, {total_players} players"
        )

        # Also save to DB (persists across deployments)
        from api.database import save_synced_roster, sync_roster_ownership
        save_synced_roster(year, all_rosters)
        print(f"[SnapshotRebuild] Saved synced roster to DB (year={year})")

        # Sync owner_manager on player_rankings in the same pass — no extra
        # Yahoo API calls needed since we already parsed every roster.
        if ownership_map:
            sync_roster_ownership(year, ownership_map)
            print(f"[SnapshotRebuild] Synced ownership for {len(ownership_map)} players")

        # Rebuild next-year snapshot
        next_year = year + 1
        try:
            from scripts.build_2027_contracts import main as rebuild_snapshot
            rebuild_snapshot()
            print(f"[SnapshotRebuild] Rebuilt year {next_year} snapshot successfully.")
        except Exception as e:
            print(f"[SnapshotRebuild] Snapshot rebuild error: {e}")

        return {
            "message": f"Synced {year} rosters and rebuilt {next_year} snapshot",
            "year": year,
            "teams": len(all_rosters),
            "total_players": total_players,
        }

    except YahooTokenError as e:
        print(f"[SnapshotRebuild] Token error: {e}")
        raise
    except Exception as e:
        print(f"[SnapshotRebuild] Error: {e}")
        raise


def _daily_roster_snapshot_rebuild_job():
    """Daily scheduler wrapper for sync_rosters_and_rebuild.

    Also syncs owner_manager on player_rankings in the same pass
    (replaces the old separate _daily_roster_ownership_sync_job).
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[SnapshotRebuild] Off-season (month {month}), skipping.")
        return

    try:
        sync_rosters_and_rebuild(now.year)
    except Exception as e:
        print(f"[SnapshotRebuild] Job failed: {e}")


def _weekly_war_report_job(target_id: str = "", dry_run: bool = False) -> dict:
    """Weekly job (Monday 21:00): generate and send weekly war report to LINE.

    Scheduled 3 hours after 18:00 AR-Rank refresh to fully clear any Yahoo
    short-term throttle window before we fetch standings/scoreboard/top players.

    Args:
        target_id: If empty, push to LINE_GROUP_ID (scheduled behavior).
                   If set (U.../C.../R...), push to that target instead — useful
                   for previewing to admin LINE without spamming the group.
        dry_run:   If True, skip LINE send entirely and just return the message
                   text for inspection.

    Returns:
        {"success": bool, "message": str (status or error), "report": str (full text)}
    """
    now = datetime.now()
    month = now.month

    # Only run during MLB season (March-October)
    if month < 3 or month > 10:
        print(f"[WarReport] Off-season (month {month}), skipping.")
        return {"success": False, "message": f"Off-season (month {month})", "report": ""}

    year = now.year
    print(f"[WarReport] Generating weekly war report for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import save_weekly_standings, get_weekly_standings
        from src.notification.line_service import send_line_group_message
        from config.settings import get_league_key
        import time

        league_key = get_league_key(year)
        if not league_key:
            print(f"[WarReport] No league key for year {year}")
            return {"success": False, "message": f"No league key for {year}", "report": ""}

        # --- 1. Get current week from league metadata ---
        meta_path = f"/league/{league_key}/metadata"
        meta_data = yahoo_api_get(meta_path)
        league_meta = meta_data.get("fantasy_content", {}).get("league", [])
        current_week = 1
        if isinstance(league_meta, list):
            for item in league_meta:
                if isinstance(item, dict) and "current_week" in item:
                    current_week = int(item["current_week"])
                    break
        # The report covers the just-completed week (current_week - 1 if games are done)
        # On Monday, Yahoo's "current_week" should be the upcoming week
        report_week = max(current_week - 1, 1)
        print(f"[WarReport] Yahoo current_week={current_week}, reporting week {report_week}")

        # --- 2. Fetch standings ---
        time.sleep(1)
        standings_path = f"/league/{league_key}/standings"
        standings_data = yahoo_api_get(standings_path)
        league_standings = standings_data.get("fantasy_content", {}).get("league", [])
        if len(league_standings) < 2:
            print("[WarReport] No standings data.")
            return {"success": False, "message": "No standings data from Yahoo", "report": ""}

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = teams_section.get("count", 0)
        try:
            team_count = int(team_count or 0)
        except (ValueError, TypeError):
            team_count = 0

        def _safe_int(v, default=0):
            try:
                return int(v) if v not in (None, "") else default
            except (ValueError, TypeError):
                return default

        def _find_section(items, key):
            """Find `key` anywhere inside the tail of team_raw (handles dict or list wrappers)."""
            for elem in items:
                if isinstance(elem, dict) and key in elem:
                    return elem[key]
                if isinstance(elem, list):
                    for sub in elem:
                        if isinstance(sub, dict) and key in sub:
                            return sub[key]
            return {}

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw or not isinstance(team_raw, list):
                continue

            # Element 0: list of info dicts (name, team_key, division_id, managers, ...)
            info_list = team_raw[0] if isinstance(team_raw[0], list) else []
            team_name = ""
            team_key = ""
            manager_name = ""
            division_id = ""
            for item in info_list:
                if not isinstance(item, dict):
                    continue
                if "name" in item:
                    team_name = str(item["name"])
                if "team_key" in item:
                    team_key = str(item["team_key"])
                if "division_id" in item:
                    division_id = str(item["division_id"])
                if "managers" in item:
                    mgrs = item["managers"]
                    if isinstance(mgrs, list) and mgrs and isinstance(mgrs[0], dict):
                        manager_name = str(mgrs[0].get("manager", {}).get("nickname", ""))

            # Element 1+: team_stats / team_points / team_standings (dict- or list-wrapped)
            standing = _find_section(team_raw[1:], "team_standings")
            if not isinstance(standing, dict):
                standing = {}

            rank = _safe_int(standing.get("rank"))
            outcome = standing.get("outcome_totals", {}) if isinstance(standing, dict) else {}
            if not isinstance(outcome, dict):
                outcome = {}
            wins = _safe_int(outcome.get("wins"))
            losses = _safe_int(outcome.get("losses"))
            ties = _safe_int(outcome.get("ties"))

            if i == 0:
                print(
                    f"[WarReport] First team sample: team_name={team_name!r} "
                    f"manager={manager_name!r} division={division_id!r} "
                    f"rank={rank} W-L-T={wins}-{losses}-{ties} "
                    f"standing_keys={list(standing.keys()) if standing else 'EMPTY'}"
                )

            current_standings.append({
                "team_name": team_name,
                "team_key": team_key,
                "manager_name": manager_name,
                "division_id": division_id,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })

        # Sort by rank; fall back to preserving Yahoo's order if ranks are all 0
        if any(s["rank"] > 0 for s in current_standings):
            current_standings.sort(key=lambda x: x["rank"] or 999)

        # Save current standings for next week's comparison
        save_weekly_standings(year, report_week, current_standings)

        # Load previous week standings for rank change comparison
        prev_standings = get_weekly_standings(year, report_week - 1) if report_week > 1 else []
        prev_rank_map = {s["manager_name"]: s["rank"] for s in prev_standings}

        # --- 3. Fetch scoreboard (matchup results) ---
        time.sleep(1)
        scoreboard_path = f"/league/{league_key}/scoreboard;week={report_week}"
        scoreboard_data = yahoo_api_get(scoreboard_path)
        league_sb = scoreboard_data.get("fantasy_content", {}).get("league", [])
        matchups: list[dict] = []
        if len(league_sb) >= 2:
            sb = league_sb[1].get("scoreboard", {})
            # Handle nested structure
            matchups_section = None
            if "0" in sb and "matchups" in sb["0"]:
                matchups_section = sb["0"]["matchups"]
            elif "matchups" in sb:
                matchups_section = sb["matchups"]

            if matchups_section:
                m_count = matchups_section.get("count", 0)
                for mi in range(m_count):
                    m_raw = matchups_section.get(str(mi), {}).get("matchup", {})
                    teams_data = m_raw.get("0", {}).get("teams", {})
                    t_count = teams_data.get("count", 0)
                    winner_key = m_raw.get("winner_team_key", "")
                    match_teams = []
                    for ti in range(t_count):
                        t_raw = teams_data.get(str(ti), {}).get("team", [])
                        if not t_raw:
                            continue
                        t_info = t_raw[0] if isinstance(t_raw, list) else []
                        t_name = ""
                        t_key = ""
                        t_mgr = ""
                        for item in t_info:
                            if isinstance(item, dict):
                                if "name" in item:
                                    t_name = item["name"]
                                if "team_key" in item:
                                    t_key = item["team_key"]
                                if "managers" in item:
                                    mgrs = item["managers"]
                                    if isinstance(mgrs, list) and mgrs:
                                        t_mgr = mgrs[0].get("manager", {}).get("nickname", "")
                        points = 0.0
                        if len(t_raw) > 1:
                            tp = t_raw[1].get("team_points", {})
                            try:
                                points = float(tp.get("total", 0))
                            except (ValueError, TypeError):
                                points = 0.0
                        match_teams.append({
                            "name": t_name,
                            "manager": t_mgr,
                            "points": points,
                            "is_winner": t_key == winner_key,
                        })
                    if len(match_teams) == 2:
                        matchups.append(match_teams)

        # --- 4. Fetch top 5 hitters and pitchers by Yahoo Points ---
        time.sleep(1)
        top_batters: list[dict] = []
        top_pitchers: list[dict] = []

        for pos_type, result_list in [("B", top_batters), ("P", top_pitchers)]:
            try:
                players_path = (
                    f"/league/{league_key}/players"
                    f";sort=PTS;sort_type=week;sort_week={report_week}"
                    f";position={pos_type};count=5;out=stats,ownership"
                )
                pdata = yahoo_api_get(players_path)
                p_league = pdata.get("fantasy_content", {}).get("league", [])
                if len(p_league) >= 2:
                    p_section = p_league[1].get("players", {})
                    for pk_idx in range(p_section.get("count", 0)):
                        p_entry = p_section.get(str(pk_idx), {}).get("player", [])
                        if not p_entry or not isinstance(p_entry, list):
                            continue
                        # Parse player info
                        p_info = {}
                        for item in (p_entry[0] if isinstance(p_entry[0], list) else [p_entry[0]]):
                            if isinstance(item, dict):
                                if "name" in item:
                                    p_info["name"] = item["name"].get("full", "")
                                if "display_position" in item:
                                    p_info["position"] = item["display_position"]
                                if "editorial_team_abbr" in item:
                                    p_info["mlb_team"] = item["editorial_team_abbr"]
                                if "ownership" in item:
                                    owner = item["ownership"]
                                    p_info["owner_team"] = owner.get("owner_team_name", "FA")
                        # Parse points
                        pts = 0.0
                        if len(p_entry) > 1:
                            player_pts = p_entry[1].get("player_points", {})
                            try:
                                pts = float(player_pts.get("total", 0))
                            except (ValueError, TypeError):
                                pts = 0.0
                        p_info["points"] = pts
                        result_list.append(p_info)
                time.sleep(1)
            except Exception as e:
                print(f"[WarReport] Error fetching top {pos_type} players: {e}")

        # --- 5. Build LINE message ---
        lines = [f"[5-Man Keeper League] 第 {report_week} 週戰報", ""]

        def _format_standing_line(s: dict, rank_override: int | None = None) -> str:
            w, l, t = s["wins"], s["losses"], s["ties"]
            mgr = s["manager_name"] or "?"
            team = s["team_name"] or "?"
            rank = rank_override if rank_override is not None else s["rank"]
            prev_rank = prev_rank_map.get(mgr)
            if prev_rank is not None and prev_rank != s["rank"] and s["rank"] > 0:
                diff = prev_rank - s["rank"]  # positive = improved
                change = f" ^{diff}" if diff > 0 else f" v{-diff}"
            else:
                change = " --"
            return f"{rank}. {team} [{mgr}] ({w}-{l}-{t}){change}"

        # Overall standings
        lines.append("-- 聯盟總排名 --")
        for s in current_standings:
            lines.append(_format_standing_line(s))
        lines.append("")

        # Division standings: group by division_id, rank within each division
        divisions: dict[str, list[dict]] = {}
        for s in current_standings:
            div = s.get("division_id", "")
            if div:
                divisions.setdefault(div, []).append(s)
        if divisions:
            for div_id in sorted(divisions.keys()):
                div_teams = sorted(divisions[div_id], key=lambda x: x["rank"] or 999)
                lines.append(f"-- 分區 {div_id} --")
                for idx, s in enumerate(div_teams, 1):
                    lines.append(_format_standing_line(s, rank_override=idx))
                lines.append("")

        # Matchup results
        if matchups:
            lines.append("-- 本週對戰 --")
            for m in matchups:
                t1, t2 = m[0], m[1]
                p1, p2 = t1["points"], t2["points"]
                m1, m2 = t1["manager"] or t1["name"], t2["manager"] or t2["name"]
                w1 = " W" if t1["is_winner"] else ""
                w2 = " W" if t2["is_winner"] else ""
                lines.append(f"{m1} {p1:.0f}{w1} - {p2:.0f}{w2} {m2}")
            lines.append("")

        # Top batters
        if top_batters:
            lines.append("-- 本週最佳打者 (Yahoo Pts) --")
            for idx, b in enumerate(top_batters[:5], 1):
                name = b.get("name", "?")
                pos = b.get("position", "")
                pts = b.get("points", 0)
                owner = b.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Top pitchers
        if top_pitchers:
            lines.append("-- 本週最佳投手 (Yahoo Pts) --")
            for idx, p in enumerate(top_pitchers[:5], 1):
                name = p.get("name", "?")
                pos = p.get("position", "")
                pts = p.get("points", 0)
                owner = p.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        lines.append("* Yahoo Fantasy Points (僅供參考)")

        # --- 6. AI commentary (OpenAI; no-op if OPENAI_API_KEY not set) ---
        try:
            from src.notification.ai_summary import generate_weekly_ai_summary
            ai_text = generate_weekly_ai_summary(
                report_week,
                current_standings,
                prev_standings,
            )
            if ai_text:
                lines.append("")
                lines.append("-- AI 短評 --")
                lines.append(ai_text)
        except Exception as e:
            print(f"[WarReport] AI summary failed (non-fatal): {e}")

        message = "\n".join(lines)

        if dry_run:
            print(f"[WarReport] Dry-run: returning week {report_week} report text.")
            return {"success": True, "message": "Dry-run (no LINE push)", "report": message}

        # Send LINE message
        if target_id:
            from src.notification.line_service import send_line_push_message
            success, error = send_line_push_message(target_id, message)
            destination = f"target {target_id[:6]}..."
        else:
            success, error = send_line_group_message(message)
            destination = "LINE group"

        if success:
            print(f"[WarReport] Week {report_week} war report sent to {destination}.")
            return {"success": True, "message": f"Sent to {destination}", "report": message}
        print(f"[WarReport] LINE send failed: {error}")
        return {"success": False, "message": f"LINE send failed: {error}", "report": message}

    except YahooTokenError as e:
        print(f"[WarReport] Token error: {e}")
        return {"success": False, "message": f"Token error: {e}", "report": ""}
    except Exception as e:
        print(f"[WarReport] Error: {e}")
        return {"success": False, "message": f"Error: {e}", "report": ""}


def _monthly_war_report_job():
    """Monthly job (1st of each month, 20:45): generate monthly summary report."""
    now = datetime.now()
    month = now.month

    # Only run during MLB season (April-October; skips March since no full month data yet)
    if month < 4 or month > 10:
        print(f"[MonthlyReport] Off-season or too early (month {month}), skipping.")
        return

    year = now.year
    report_month = month - 1  # Report covers the previous month
    month_names = {3: "3月", 4: "4月", 5: "5月", 6: "6月",
                   7: "7月", 8: "8月", 9: "9月", 10: "10月"}
    month_label = month_names.get(report_month, f"{report_month}月")

    print(f"[MonthlyReport] Generating {month_label} report for {year}...")

    try:
        from api.yahoo_service import yahoo_api_get, YahooTokenError
        from api.database import get_weekly_standings
        from src.notification.line_service import send_line_group_message
        from config.settings import get_league_key
        import time
        import json
        from pathlib import Path

        league_key = get_league_key(year)
        if not league_key:
            print(f"[MonthlyReport] No league key for year {year}")
            return

        # --- 1. Get current week to determine which weeks belong to the report month ---
        meta_path = f"/league/{league_key}/metadata"
        meta_data = yahoo_api_get(meta_path)
        league_meta = meta_data.get("fantasy_content", {}).get("league", [])
        current_week = 1
        start_date_str = ""
        if isinstance(league_meta, list):
            for item in league_meta:
                if isinstance(item, dict):
                    if "current_week" in item:
                        current_week = int(item["current_week"])
                    if "start_date" in item:
                        start_date_str = item["start_date"]

        # Estimate which weeks fall in the report month
        # Yahoo seasons typically start late March; each week is 7 days
        # We use the weekly_standings table to find weeks with data in the report month
        report_week_end = current_week - 1  # Last completed week

        # --- 2. Fetch current standings for month-end snapshot ---
        time.sleep(1)
        standings_path = f"/league/{league_key}/standings"
        standings_data = yahoo_api_get(standings_path)
        league_standings = standings_data.get("fantasy_content", {}).get("league", [])
        if len(league_standings) < 2:
            print("[MonthlyReport] No standings data.")
            return

        teams_section = league_standings[1].get("standings", [{}])[0].get("teams", {})
        team_count = teams_section.get("count", 0)

        current_standings: list[dict] = []
        for i in range(team_count):
            team_raw = teams_section.get(str(i), {}).get("team", [])
            if not team_raw:
                continue
            info_list = team_raw[0] if isinstance(team_raw, list) else []
            team_name = ""
            manager_name = ""
            for item in info_list:
                if isinstance(item, dict):
                    if "name" in item:
                        team_name = item["name"]
                    if "managers" in item:
                        mgrs = item["managers"]
                        if isinstance(mgrs, list) and mgrs:
                            manager_name = mgrs[0].get("manager", {}).get("nickname", "")
            standing = {}
            if len(team_raw) > 1:
                standing = team_raw[1].get("team_standings", {})
            rank = int(standing.get("rank", 0))
            record = standing.get("outcome_totals", {})
            wins = int(record.get("wins", 0))
            losses = int(record.get("losses", 0))
            ties = int(record.get("ties", 0))
            current_standings.append({
                "team_name": team_name,
                "manager_name": manager_name,
                "rank": rank,
                "wins": wins,
                "losses": losses,
                "ties": ties,
            })
        current_standings.sort(key=lambda x: x["rank"])

        # Find the earliest week of the report month from weekly_standings
        # We look for the week saved ~4 weeks ago as start-of-month reference
        month_start_week = max(report_week_end - 4, 1)
        prev_month_standings = get_weekly_standings(year, month_start_week)
        prev_rank_map = {s["manager_name"]: s["rank"] for s in prev_month_standings}
        # Also compute W-L changes (monthly record)
        prev_record_map = {
            s["manager_name"]: (s.get("wins", 0), s.get("losses", 0), s.get("ties", 0))
            for s in prev_month_standings
        }

        # --- 3. Monthly matchup summary (aggregate all weeks in the month) ---
        time.sleep(1)
        team_monthly_record: dict[str, dict] = {}  # manager -> {w, l, t}
        for wk in range(month_start_week + 1, report_week_end + 1):
            try:
                sb_path = f"/league/{league_key}/scoreboard;week={wk}"
                sb_data = yahoo_api_get(sb_path)
                sb_league = sb_data.get("fantasy_content", {}).get("league", [])
                if len(sb_league) < 2:
                    continue
                sb = sb_league[1].get("scoreboard", {})
                matchups_section = None
                if "0" in sb and "matchups" in sb["0"]:
                    matchups_section = sb["0"]["matchups"]
                elif "matchups" in sb:
                    matchups_section = sb["matchups"]
                if not matchups_section:
                    continue

                m_count = matchups_section.get("count", 0)
                for mi in range(m_count):
                    m_raw = matchups_section.get(str(mi), {}).get("matchup", {})
                    teams_data = m_raw.get("0", {}).get("teams", {})
                    winner_key = m_raw.get("winner_team_key", "")
                    t_count = teams_data.get("count", 0)

                    match_info = []
                    for ti in range(t_count):
                        t_raw = teams_data.get(str(ti), {}).get("team", [])
                        if not t_raw:
                            continue
                        t_info = t_raw[0] if isinstance(t_raw, list) else []
                        t_key = ""
                        t_mgr = ""
                        for item in t_info:
                            if isinstance(item, dict):
                                if "team_key" in item:
                                    t_key = item["team_key"]
                                if "managers" in item:
                                    mgrs = item["managers"]
                                    if isinstance(mgrs, list) and mgrs:
                                        t_mgr = mgrs[0].get("manager", {}).get("nickname", "")
                        pts = 0.0
                        if len(t_raw) > 1:
                            tp = t_raw[1].get("team_points", {})
                            try:
                                pts = float(tp.get("total", 0))
                            except (ValueError, TypeError):
                                pass
                        match_info.append({"key": t_key, "mgr": t_mgr, "pts": pts})

                    if len(match_info) == 2:
                        for mi_t in match_info:
                            mgr = mi_t["mgr"]
                            if mgr not in team_monthly_record:
                                team_monthly_record[mgr] = {"w": 0, "l": 0, "t": 0}
                            if mi_t["key"] == winner_key:
                                team_monthly_record[mgr]["w"] += 1
                            elif winner_key:
                                team_monthly_record[mgr]["l"] += 1
                            else:
                                team_monthly_record[mgr]["t"] += 1

                time.sleep(0.6)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10)
                else:
                    print(f"[MonthlyReport] Scoreboard error week {wk}: {e}")

        # --- 4. Top 5 hitters and pitchers (month stats) ---
        time.sleep(1)
        top_batters: list[dict] = []
        top_pitchers: list[dict] = []

        for pos_type, result_list in [("B", top_batters), ("P", top_pitchers)]:
            try:
                # Use season sort_type=lastmonth if available, otherwise season
                players_path = (
                    f"/league/{league_key}/players"
                    f";sort=PTS;sort_type=lastmonth"
                    f";position={pos_type};count=5;out=stats,ownership"
                )
                pdata = yahoo_api_get(players_path)
                p_league = pdata.get("fantasy_content", {}).get("league", [])
                if len(p_league) >= 2:
                    p_section = p_league[1].get("players", {})
                    for pk_idx in range(p_section.get("count", 0)):
                        p_entry = p_section.get(str(pk_idx), {}).get("player", [])
                        if not p_entry or not isinstance(p_entry, list):
                            continue
                        p_info = {}
                        for item in (p_entry[0] if isinstance(p_entry[0], list) else [p_entry[0]]):
                            if isinstance(item, dict):
                                if "name" in item:
                                    p_info["name"] = item["name"].get("full", "")
                                if "display_position" in item:
                                    p_info["position"] = item["display_position"]
                                if "editorial_team_abbr" in item:
                                    p_info["mlb_team"] = item["editorial_team_abbr"]
                                if "ownership" in item:
                                    owner = item["ownership"]
                                    p_info["owner_team"] = owner.get("owner_team_name", "FA")
                        pts = 0.0
                        if len(p_entry) > 1:
                            player_pts = p_entry[1].get("player_points", {})
                            try:
                                pts = float(player_pts.get("total", 0))
                            except (ValueError, TypeError):
                                pts = 0.0
                        p_info["points"] = pts
                        result_list.append(p_info)
                time.sleep(1)
            except Exception as e:
                print(f"[MonthlyReport] Error fetching top {pos_type}: {e}")

        # --- 5. Transaction summary from JSON file ---
        tx_summary: list[str] = []
        try:
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
            tx_file = data_dir / f"yahoo_{year}_transactions.json"
            if tx_file.exists():
                with open(tx_file, "r", encoding="utf-8") as f:
                    tx_data = json.load(f)
                all_tx = tx_data.get("transactions", [])

                # Filter transactions from the report month
                month_trades = 0
                month_adds = 0
                month_drops = 0
                notable_trades: list[str] = []

                for tx in all_tx:
                    ts = tx.get("timestamp", "")
                    if not ts:
                        continue
                    try:
                        from datetime import datetime as dt_cls
                        tx_date = dt_cls.fromtimestamp(int(ts))
                        if tx_date.year != year or tx_date.month != report_month:
                            continue
                    except (ValueError, TypeError):
                        continue

                    tx_type = tx.get("type", "")
                    if tx_type == "trade":
                        month_trades += 1
                        # Collect notable trade details (first 3)
                        if len(notable_trades) < 3:
                            players = tx.get("players", [])
                            names = [p.get("name", "?") for p in players[:4]]
                            notable_trades.append(", ".join(names))
                    elif tx_type in ("add", "add/drop"):
                        month_adds += 1
                        if "drop" in tx_type:
                            month_drops += 1
                    elif tx_type == "drop":
                        month_drops += 1

                if month_trades or month_adds or month_drops:
                    tx_summary.append(f"交易: {month_trades} 筆 | 撿人: {month_adds} 筆 | 釋出: {month_drops} 筆")
                    for nt in notable_trades:
                        tx_summary.append(f"  Trade: {nt}")
        except Exception as e:
            print(f"[MonthlyReport] Transaction summary error: {e}")

        # --- 6. Build LINE message ---
        lines = [f"[5-Man Keeper League] {year} {month_label}月報", ""]

        # Standings with monthly rank change
        lines.append("-- 排名 --")
        for s in current_standings:
            w, l, t = s["wins"], s["losses"], s["ties"]
            mgr = s["manager_name"]
            rank = s["rank"]
            prev_rank = prev_rank_map.get(mgr)
            if prev_rank is not None and prev_rank != rank:
                diff = prev_rank - rank
                change = f" ^{diff}" if diff > 0 else f" v{-diff}"
            else:
                change = " --"
            lines.append(f"{rank}. {mgr} ({w}-{l}-{t}){change}")
        lines.append("")

        # Monthly team records
        if team_monthly_record:
            lines.append(f"-- {month_label}戰績 --")
            sorted_monthly = sorted(
                team_monthly_record.items(),
                key=lambda x: (x[1]["w"], -x[1]["l"]),
                reverse=True,
            )
            for mgr, rec in sorted_monthly:
                lines.append(f"{mgr}: {rec['w']}-{rec['l']}-{rec['t']}")
            lines.append("")

        # Top batters
        if top_batters:
            lines.append(f"-- {month_label}最佳打者 (Yahoo Pts) --")
            for idx, b in enumerate(top_batters[:5], 1):
                name = b.get("name", "?")
                pos = b.get("position", "")
                pts = b.get("points", 0)
                owner = b.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Top pitchers
        if top_pitchers:
            lines.append(f"-- {month_label}最佳投手 (Yahoo Pts) --")
            for idx, p in enumerate(top_pitchers[:5], 1):
                name = p.get("name", "?")
                pos = p.get("position", "")
                pts = p.get("points", 0)
                owner = p.get("owner_team", "FA")
                lines.append(f"{idx}. {name} ({pos}) - {pts:.1f} pts [{owner}]")
            lines.append("")

        # Transaction summary
        if tx_summary:
            lines.append(f"-- {month_label}交易摘要 --")
            lines.extend(tx_summary)
            lines.append("")

        lines.append("* Yahoo Fantasy Points (僅供參考)")

        message = "\n".join(lines)

        success, error = send_line_group_message(message)
        if success:
            print(f"[MonthlyReport] {month_label} report sent to LINE.")
        else:
            print(f"[MonthlyReport] LINE send failed: {error}")

    except YahooTokenError as e:
        print(f"[MonthlyReport] Token error: {e}")
    except Exception as e:
        print(f"[MonthlyReport] Error: {e}")


def _prospect_ranking_update_job():
    """Annual job (Aug 15): fetch MLB Pipeline prospect data and compare with league R-contract players."""
    now = datetime.now()
    # Only run on August 15
    if now.month != 8 or now.day != 15:
        return

    year = now.year
    print(f"[ProspectUpdate] Fetching MLB prospect rankings for {year}...")

    try:
        import httpx
        import time
        from src.notification.line_service import send_line_group_message
        from src.notification.rookie_monitor import _load_r_contract_players

        MLB_BASE = "https://statsapi.mlb.com/api/v1"

        # --- 1. Fetch MLB Pipeline prospect data ---
        # Try the draft/prospects endpoint for the current year
        prospects: list[dict] = []
        try:
            resp = httpx.get(
                f"{MLB_BASE}/draft/prospects/{year}",
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse prospects from response
            prospect_list = data.get("prospects", [])
            for p in prospect_list:
                person = p.get("person", {})
                if not person:
                    continue
                prospects.append({
                    "name": person.get("fullName", ""),
                    "mlb_id": person.get("id"),
                    "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                    "team": p.get("team", {}).get("abbreviation",
                            person.get("currentTeam", {}).get("abbreviation", "")),
                    "rank": p.get("rank", p.get("pickNumber", 0)),
                })
        except Exception as e:
            print(f"[ProspectUpdate] draft/prospects endpoint error: {e}")

        # Also try the people/search approach for a broader list
        if not prospects:
            print("[ProspectUpdate] Trying alternative: top prospect search...")
            try:
                # MLB Stats API: search for prospect-tagged players
                resp = httpx.get(
                    f"{MLB_BASE}/people/search",
                    params={
                        "names": "",
                        "sportId": 11,  # Minor leagues
                        "season": year,
                        "hydrate": "currentTeam",
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    people = resp.json().get("people", [])
                    for person in people[:200]:
                        prospects.append({
                            "name": person.get("fullName", ""),
                            "mlb_id": person.get("id"),
                            "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                            "team": person.get("currentTeam", {}).get("abbreviation", ""),
                            "rank": 0,
                        })
            except Exception as e:
                print(f"[ProspectUpdate] Alternative search error: {e}")

        print(f"[ProspectUpdate] Fetched {len(prospects)} prospects from MLB API")

        # --- 2. Load league R-contract players ---
        r_players = _load_r_contract_players(year)
        if not r_players:
            print("[ProspectUpdate] No R-contract players found in league")
            # Still send a summary even if no R players
            r_players = []

        print(f"[ProspectUpdate] League has {len(r_players)} R-contract players")

        # --- 3. Cross-reference: check which R players appear in prospect list ---
        # Normalize names for matching (lowercase, strip accents, etc.)
        prospect_name_map: dict[str, dict] = {}
        for p in prospects:
            name_key = p["name"].lower().strip()
            prospect_name_map[name_key] = p
            # Also try last name only for fuzzy matching
            parts = name_key.split()
            if len(parts) >= 2:
                prospect_name_map[parts[-1]] = p

        matched: list[dict] = []
        unmatched: list[dict] = []

        for rp in r_players:
            rp_name = rp["name"].lower().strip()
            # Clean parenthetical nicknames: "Roki Sasaki (佐々木朗希)" -> "roki sasaki"
            clean_name = rp_name.split("(")[0].strip()

            match = prospect_name_map.get(clean_name)
            if not match:
                # Try last name
                parts = clean_name.split()
                if len(parts) >= 2:
                    match = prospect_name_map.get(parts[-1])

            if not match:
                # Try MLB Stats API person search for individual player
                try:
                    search_name = rp["name"].split("(")[0].strip()
                    resp = httpx.get(
                        f"{MLB_BASE}/people/search",
                        params={"names": search_name, "hydrate": "currentTeam"},
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        people = resp.json().get("people", [])
                        if people:
                            person = people[0]
                            match = {
                                "name": person.get("fullName", ""),
                                "mlb_id": person.get("id"),
                                "position": person.get("primaryPosition", {}).get("abbreviation", ""),
                                "team": person.get("currentTeam", {}).get("abbreviation", ""),
                                "rank": 0,
                                "age": person.get("currentAge"),
                                "debut": person.get("mlbDebutDate", ""),
                            }
                    time.sleep(0.5)
                except Exception:
                    pass

            if match:
                matched.append({
                    **rp,
                    "prospect_info": match,
                })
            else:
                unmatched.append(rp)

        # --- 4. Build and send LINE notification ---
        lines = [
            f"[5-Man Keeper League] {year} 新秀排名更新",
            f"MLB Prospect Rankings Update",
            f"",
            f"資料來源: MLB Stats API ({now.strftime('%Y-%m-%d')})",
            f"聯盟 R 約球員: {len(r_players)} 名",
            f"",
        ]

        if matched:
            lines.append("-- 聯盟 R 約球員 MLB 資訊 --")
            for m in matched:
                pi = m["prospect_info"]
                rank_str = f"#{pi['rank']}" if pi.get("rank") else ""
                age_str = f", {pi['age']}歲" if pi.get("age") else ""
                debut_str = f" (已升大聯盟 {pi['debut']})" if pi.get("debut") else ""
                lines.append(
                    f"  {m['name']} ({pi.get('position', m['position'])}/{pi.get('team', m['mlb_team'])})"
                    f" - {m['owner_manager']} 隊"
                )
                if rank_str or age_str or debut_str:
                    lines.append(f"    {rank_str}{age_str}{debut_str}")
            lines.append("")

        if unmatched:
            lines.append("-- 未在 MLB API 中找到 --")
            for u in unmatched:
                lines.append(
                    f"  {u['name']} ({u['position']}/{u['mlb_team']}) - {u['owner_manager']} 隊"
                )
            lines.append("")

        if not r_players:
            lines.append("目前聯盟沒有 R 約球員。")
            lines.append("")

        lines.append(f"API 取得 {len(prospects)} 名 prospect 資料")

        message = "\n".join(lines)

        success, error = send_line_group_message(message)
        if success:
            print(f"[ProspectUpdate] LINE notification sent. "
                  f"Matched: {len(matched)}, Unmatched: {len(unmatched)}")
        else:
            print(f"[ProspectUpdate] LINE send failed: {error}")

    except Exception as e:
        print(f"[ProspectUpdate] Error: {e}")


def start_scheduler():
    """Start the background scheduler.

    Jobs:
    1. Keeper reminder: daily cron during keeper period
    2. Rookie call-up monitor: daily cron during MLB season
    3. Daily AR-Rank + season stats refresh: 18:00 during MLB season (single pass)
    4. Daily player status update + injury notification: during MLB season
    5. Daily transaction fetch: daily during MLB season
    6. Daily roster + snapshot + ownership sync: 00:30 Taiwan time (merged)
    7. Weekly war report: Monday 21:00 during MLB season
    8. Monthly war report: 1st of each month 20:45 during MLB season
    9. Prospect ranking update: Aug 15 annually, fetch MLB API + compare R players
    """
    global _scheduler

    # Determine reminder mode
    if KEEPER_REMINDER_START:
        mode = "legacy"
        period_desc = f"{KEEPER_REMINDER_START} ~ {KEEPER_REMINDER_END or 'no end'}"
    else:
        mode = "annual"
        period_desc = f"every year {REMINDER_MONTH}/{REMINDER_START_DAY} ~ {REMINDER_MONTH}/{REMINDER_END_DAY}"

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[Scheduler] apscheduler not installed, scheduler disabled.")
        return

    _scheduler = BackgroundScheduler()

    # Job 1: Keeper reminders
    _scheduler.add_job(
        _daily_reminder_job,
        CronTrigger(hour=REMINDER_CRON_HOUR, timezone=REMINDER_CRON_TZ),
        id="keeper_reminder",
        replace_existing=True,
    )

    # Job 2: Rookie call-up monitor
    if ROOKIE_MONITOR_ENABLED:
        _scheduler.add_job(
            _daily_rookie_monitor_job,
            CronTrigger(hour=REMINDER_CRON_HOUR, timezone=REMINDER_CRON_TZ),
            id="rookie_monitor",
            replace_existing=True,
        )

    # Job 3: Daily AR-Rank + season stats refresh
    # 18:00 Taiwan = 6:00 AM ET — after all US games end + Yahoo stats processed
    _scheduler.add_job(
        _daily_ar_rank_refresh_job,
        CronTrigger(
            hour=18,
            minute=0,
            timezone=REMINDER_CRON_TZ,
        ),
        id="ar_rank_refresh",
        replace_existing=True,
    )

    # Job 4: Daily player status update (IL/DTD/NA/O)
    _scheduler.add_job(
        _daily_player_status_job,
        CronTrigger(
            hour=REMINDER_CRON_HOUR,
            minute=30,
            timezone=REMINDER_CRON_TZ,
        ),
        id="player_status_update",
        replace_existing=True,
    )

    # Job 5: Daily transaction fetch (during MLB season)
    _scheduler.add_job(
        _daily_transaction_fetch_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=15,
            timezone=REMINDER_CRON_TZ,
        ),
        id="transaction_fetch",
        replace_existing=True,
    )

    # Job 6: Daily roster fetch + snapshot rebuild + ownership sync
    # (merged: the separate 00:30 ownership sync was duplicating these 16 roster fetches)
    _scheduler.add_job(
        _daily_roster_snapshot_rebuild_job,
        CronTrigger(
            hour=DAILY_SYNC_HOUR,
            minute=30,
            timezone=REMINDER_CRON_TZ,
        ),
        id="roster_snapshot_rebuild",
        replace_existing=True,
    )

    # Job 7: Weekly war report (Monday 21:00 - 3hr buffer after 18:00 AR-Rank refresh)
    _scheduler.add_job(
        _weekly_war_report_job,
        CronTrigger(
            day_of_week="mon",
            hour=21,
            minute=0,
            timezone=REMINDER_CRON_TZ,
        ),
        id="war_report",
        replace_existing=True,
    )

    # Job 8: Monthly war report (1st of each month at 20:45)
    _scheduler.add_job(
        _monthly_war_report_job,
        CronTrigger(
            day=1,
            hour=20,
            minute=45,
            timezone=REMINDER_CRON_TZ,
        ),
        id="monthly_report",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Started ({mode} mode). "
          f"Check daily at {REMINDER_CRON_HOUR}:00 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Keeper reminders every {REMINDER_INTERVAL_DAYS} days "
          f"(period: {period_desc})")
    if ROOKIE_MONITOR_ENABLED:
        print(f"[Scheduler] Rookie monitor active "
              f"(months {ROOKIE_MONITOR_START_MONTH}-{ROOKIE_MONITOR_END_MONTH})")
    print("[Scheduler] Daily AR-Rank + stats refresh: 18:00")
    print("[Scheduler] Daily player status update + injury notification: 12:30 PM")
    print(f"[Scheduler] Daily transaction fetch: {DAILY_SYNC_HOUR}:15 {REMINDER_CRON_TZ}")
    print(f"[Scheduler] Daily roster + snapshot + ownership sync: {DAILY_SYNC_HOUR}:30 {REMINDER_CRON_TZ}")
    print("[Scheduler] Weekly war report: every Monday 21:00")
    # Job 10: Annual prospect ranking update (Aug 15)
    _scheduler.add_job(
        _prospect_ranking_update_job,
        CronTrigger(
            month=8,
            day=15,
            hour=19,
            timezone=REMINDER_CRON_TZ,
        ),
        id="prospect_update",
        replace_existing=True,
    )

    print("[Scheduler] Monthly war report: 1st of each month 20:45")
    print("[Scheduler] Prospect ranking update: Aug 15 19:00")


def stop_scheduler():
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")
        _scheduler = None
