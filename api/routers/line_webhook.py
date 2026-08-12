"""
LINE webhook — text-command interface for the Commissioner.

Replies use the event's reply token, which does not consume the monthly push
quota, so testing reports from LINE is free. The webhook URL is public;
every command is gated by an explicit user-id whitelist. Unknown senders only
ever learn their own user id — that reply is the intended bootstrap path for
configuring the whitelist in the first place (message the bot, read your id,
set it as an env var).

Env vars:
    LINE_CHANNEL_SECRET   webhook signature key (LINE Developers Console)
    LINE_ADMIN_USER_IDS   comma-separated whitelist of admin user ids
    LINE_ADMIN_USER_ID    legacy single-admin var, also honoured
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

router = APIRouter()

HELP_TEXT = "\n".join([
    "可用指令：",
    "戰報　－ 本週戰報預覽（不推群組）",
    "月報　－ 本月戰報預覽（不推群組）",
    "雷達　－ FA 雷達打者 Top 10",
    "雷達投手 － FA 雷達投手 Top 10",
    "排程　－ 排程狀態與下次執行時間",
    "",
    "以上皆為 reply，不消耗推播配額。",
])


def _admin_ids() -> set[str]:
    """Whitelist read at call time so a redeployed env change needs no code."""
    raw = ",".join([
        os.getenv("LINE_ADMIN_USER_IDS", ""),
        os.getenv("LINE_ADMIN_USER_ID", ""),
    ])
    return {token.strip() for token in raw.split(",") if token.strip()}


def verify_line_signature(body: bytes, signature: str, secret: str) -> bool:
    """HMAC-SHA256 of the raw body, base64 encoded — per LINE Messaging API."""
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _format_radar(role: str) -> str:
    from datetime import date

    from src.analytics.fa_radar import build_radar

    data = build_radar(year=date.today().year, as_of=date.today(), role=role,
                       window_days=15, limit=10)
    label = "打者" if role == "batter" else "投手"
    lines = [f"FA 雷達（{label}，近 15 天）",
             f"區間 {data['window']['start']} ~ {data['window']['end']}"]
    players = data.get("players") or []
    if not players:
        lines += [""] + (data.get("notes") or ["目前沒有符合條件的球員。"])
        return "\n".join(lines)
    for i, p in enumerate(players, 1):
        reasons = "、".join(p.get("reasons") or [])
        lines.append(f"{i}. {p['name']}（{p['score']} 分）")
        if reasons:
            lines.append(f"　{reasons}")
    return "\n".join(lines)


def _format_scheduler_status() -> str:
    from src.notification.scheduler import get_scheduler_status

    status = get_scheduler_status()
    lines = [f"排程器：{'運作中' if status.get('running') else '未啟動'}"]
    for job in status.get("jobs", []):
        next_run = (job.get("next_run_time") or "-").replace("T", " ")[:16]
        lines.append(f"{job['id']}：{next_run}")

    try:
        from api.database import get_recent_job_runs

        runs = get_recent_job_runs(limit=5)
        if runs:
            lines.append("")
            lines.append("最近執行：")
            for r in runs:
                at = r.get("recorded_at")
                at_text = at.isoformat()[:16].replace("T", " ") if at else "-"
                lines.append(f"{r['job_id']} {r['status']} @ {at_text}")
    except Exception as e:
        lines.append(f"(執行紀錄讀取失敗：{e})")
    return "\n".join(lines)


def _run_command(text: str) -> str:
    """Resolve one admin command to its reply text. Never raises."""
    command = (text or "").strip()
    try:
        if command == "戰報":
            from src.notification.scheduler import _weekly_war_report_job

            result = _weekly_war_report_job(dry_run=True)
            return result.get("report") or f"戰報產生失敗：{result.get('message')}"
        if command == "月報":
            from src.notification.scheduler import _monthly_war_report_job

            result = _monthly_war_report_job(dry_run=True)
            return result.get("report") or f"月報產生失敗：{result.get('message')}"
        if command == "雷達":
            return _format_radar("batter")
        if command == "雷達投手":
            return _format_radar("pitcher")
        if command == "排程":
            return _format_scheduler_status()
        return HELP_TEXT
    except Exception as e:
        return f"指令執行失敗：{e}"


def _handle_text_event(user_id: str, text: str, reply_token: str) -> None:
    """Background worker: authorize, run, reply (push fallback for admins).

    Report generation can outlive the ~1 minute reply-token validity, so a
    failed reply falls back to a push — that costs one quota unit, but only
    for whitelisted admins.
    """
    from src.notification.line_service import (
        send_line_push_message,
        send_line_reply_message,
    )

    if user_id not in _admin_ids():
        send_line_reply_message(reply_token, "\n".join([
            "你的 LINE user id：",
            user_id or "(讀不到 user id)",
            "",
            "此 bot 的指令僅限管理者使用。",
            "如你是管理者，請將上方 id 設到",
            "LINE_ADMIN_USER_IDS 環境變數後再試。",
        ]))
        return

    message = _run_command(text)
    ok, err = send_line_reply_message(reply_token, message)
    if not ok:
        ok2, err2 = send_line_push_message(user_id, message)
        print(
            f"[LineWebhook] reply failed ({err}); "
            f"push fallback {'sent' if ok2 else f'failed: {err2}'}",
            flush=True,
        )


@router.post("/webhook")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(default=""),
):
    """Receive LINE events. Returns 200 fast; commands run in the background."""
    secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if not secret:
        # Explicit degradation: without the secret every request is unverifiable.
        raise HTTPException(status_code=503, detail="LINE_CHANNEL_SECRET not configured")

    body = await request.body()
    if not verify_line_signature(body, x_line_signature, secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue
        message = event.get("message") or {}
        if message.get("type") != "text":
            continue
        reply_token = event.get("replyToken") or ""
        if not reply_token:
            continue
        user_id = (event.get("source") or {}).get("userId") or ""
        background_tasks.add_task(
            _handle_text_event, user_id, message.get("text") or "", reply_token
        )

    return {"ok": True}
