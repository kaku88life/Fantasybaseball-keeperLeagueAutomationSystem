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


def generate_monthly_ai_summary(
    month_label: str,
    current_standings: list[dict[str, Any]],
    prev_month_standings: list[dict[str, Any]],
    monthly_record: dict[str, dict[str, int]] | None = None,
) -> str:
    """Return 5-sentence Traditional Chinese monthly commentary, or "" on skip/error.

    Similar to weekly but framed around the month's story: biggest risers/fallers,
    hottest/coldest teams (by monthly W-L), and playoff picture.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("[AISummary] OPENAI_API_KEY not set, skipping monthly.")
        return ""

    changes: list[dict[str, Any]] = []
    if prev_month_standings:
        changes = _compute_rank_changes(current_standings, prev_month_standings)

    standings_lines: list[str] = []
    change_by_mgr = {c["manager"]: c for c in changes}
    for s in current_standings:
        mgr = s["manager_name"]
        c = change_by_mgr.get(mgr)
        if c and c["diff"] != 0:
            sign = "+" if c["diff"] > 0 else ""
            delta = f"（月初 #{c['prev_rank']}，{sign}{c['diff']}）"
        elif c:
            delta = "（排名持平）"
        else:
            delta = ""
        standings_lines.append(
            f"{s['rank']}. {mgr} ({s['wins']}-{s['losses']}-{s['ties']}){delta}"
        )

    top3 = [c for c in changes if c["diff"] != 0][:3]
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
        swings_block = "（本月無顯著排名變化）"

    monthly_block = ""
    if monthly_record:
        sorted_monthly = sorted(
            monthly_record.items(),
            key=lambda x: (x[1].get("w", 0), -x[1].get("l", 0)),
            reverse=True,
        )
        top_hot = sorted_monthly[:3]
        top_cold = sorted_monthly[-3:]
        hot_lines = [
            f"- {mgr}：{rec.get('w', 0)}-{rec.get('l', 0)}-{rec.get('t', 0)}"
            for mgr, rec in top_hot
        ]
        cold_lines = [
            f"- {mgr}：{rec.get('w', 0)}-{rec.get('l', 0)}-{rec.get('t', 0)}"
            for mgr, rec in top_cold
        ]
        monthly_block = (
            f"本月戰績最佳：\n{chr(10).join(hot_lines)}\n\n"
            f"本月戰績最差：\n{chr(10).join(cold_lines)}\n\n"
        )

    prompt = (
        "你是繁體中文體育主播，為 16 隊 Fantasy Baseball Keeper League 撰寫本月戰報短評。\n"
        f"請依以下資料，以繁體中文寫出**恰好 5 句**短評，每句換行分隔；"
        "風格生動有梗但不失專業，不加編號或項目符號。\n\n"
        f"{month_label}結束時聯盟排名：\n"
        f"{chr(10).join(standings_lines)}\n\n"
        f"本月排名波動最大的三隊：\n"
        f"{swings_block}\n\n"
        f"{monthly_block}"
        "限制：\n"
        "- 恰好 5 句，每句不超過 40 字\n"
        "- 繁體中文\n"
        "- 聚焦本月故事線（升降最大、最熱/冷隊伍、季後賽門票競爭）\n"
        "- 不要重複排名數字，不要再列戰績（上面已顯示）\n"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.8,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or ""
    except Exception as e:
        print(f"[AISummary] Monthly OpenAI call failed: {e}")
        return ""
