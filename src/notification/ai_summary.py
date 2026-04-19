"""OpenAI-powered weekly war report commentary.

Generates a 5-sentence Traditional Chinese short commentary based on
this week's standings vs last week's + top 3 biggest rank swings.

Fails gracefully (returns empty string) so the underlying war report
still sends even if OpenAI is down or unconfigured.

Env vars:
- OPENAI_API_KEY   : required; if missing, this module is a no-op
- OPENAI_MODEL     : optional; defaults to gpt-4o-mini
"""
from __future__ import annotations

import os
from typing import Any


def _compute_rank_changes(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return per-manager rank change records, sorted by |diff| descending."""
    prev_map = {s["manager_name"]: s["rank"] for s in previous}
    changes: list[dict[str, Any]] = []
    for s in current:
        mgr = s["manager_name"]
        prev_rank = prev_map.get(mgr)
        if prev_rank is None:
            continue
        diff = prev_rank - s["rank"]
        changes.append({
            "manager": mgr,
            "current_rank": s["rank"],
            "prev_rank": prev_rank,
            "diff": diff,
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "ties": s.get("ties", 0),
        })
    changes.sort(key=lambda c: (abs(c["diff"]), c["diff"]), reverse=True)
    return changes


def generate_weekly_ai_summary(
    week: int,
    current_standings: list[dict[str, Any]],
    previous_standings: list[dict[str, Any]],
) -> str:
    """Return 5-sentence Traditional Chinese commentary, or empty string on skip/error."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("[AISummary] OPENAI_API_KEY not set, skipping.")
        return ""

    if not previous_standings:
        print("[AISummary] No previous-week standings (first week?), skipping.")
        return ""

    changes = _compute_rank_changes(current_standings, previous_standings)
    if not changes:
        return ""

    top3 = [c for c in changes if c["diff"] != 0][:3]

    standings_lines: list[str] = []
    change_by_mgr = {c["manager"]: c for c in changes}
    for s in current_standings:
        mgr = s["manager_name"]
        c = change_by_mgr.get(mgr)
        if c and c["diff"] != 0:
            sign = "+" if c["diff"] > 0 else ""
            delta = f"（上週 #{c['prev_rank']}，{sign}{c['diff']}）"
        elif c:
            delta = "（排名持平）"
        else:
            delta = ""
        standings_lines.append(
            f"{s['rank']}. {mgr} ({s['wins']}-{s['losses']}-{s['ties']}){delta}"
        )

    if top3:
        swings_lines = []
        for c in top3:
            direction = "上升" if c["diff"] > 0 else "下滑"
            swings_lines.append(
                f"- {c['manager']}：#{c['prev_rank']} -> #{c['current_rank']}"
                f"（{direction} {abs(c['diff'])} 名）"
            )
        swings_block = "\n".join(swings_lines)
    else:
        swings_block = "（本週無顯著排名變化）"

    prompt = (
        "你是繁體中文體育主播，為 16 隊 Fantasy Baseball Keeper League 撰寫本週戰報短評。\n"
        f"請依以下資料，以繁體中文寫出**恰好 5 句**短評，每句換行分隔；"
        "風格生動有梗但不失專業，不加編號或項目符號。\n\n"
        f"第 {week} 週目前排名：\n"
        f"{chr(10).join(standings_lines)}\n\n"
        "本週排名波動最大的三隊：\n"
        f"{swings_block}\n\n"
        "限制：\n"
        "- 恰好 5 句，每句不超過 40 字\n"
        "- 繁體中文\n"
        "- 聚焦波動最大的隊伍與整體局勢\n"
        "- 不要重複排名數字，不要再列戰績（上面已顯示）\n"
    )

    try:
        from openai import OpenAI  # lazy import
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.8,
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            return ""
        return content
    except Exception as e:
        print(f"[AISummary] OpenAI call failed: {e}")
        return ""
