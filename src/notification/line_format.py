"""
Shared plain-text layout helpers for LINE messages.
"""
from __future__ import annotations


LINE_REPORT_PAGE_WIDTH = 28


def report_width() -> int:
    """Return the LINE-friendly visual width used by notification messages."""
    return LINE_REPORT_PAGE_WIDTH


def visual_width(s: str) -> int:
    """Approximate display width: CJK/fullwidth characters use 2 cells."""
    w = 0
    for c in s:
        o = ord(c)
        if (
            0x1100 <= o <= 0x115F
            or 0x2600 <= o <= 0x26FF
            or 0x2700 <= o <= 0x27BF
            or 0x2B00 <= o <= 0x2BFF
            or 0x2E80 <= o <= 0x303E
            or 0x3041 <= o <= 0x33FF
            or 0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF
            or 0xA000 <= o <= 0xA4CF
            or 0xAC00 <= o <= 0xD7A3
            or 0xF900 <= o <= 0xFAFF
            or 0xFE30 <= o <= 0xFE4F
            or 0xFF00 <= o <= 0xFF60
            or 0xFFE0 <= o <= 0xFFE6
            or 0x1F300 <= o <= 0x1FAFF
        ):
            w += 2
        else:
            w += 1
    return w


def center_line(text: str, width: int | None = None) -> str:
    """Center text using fullwidth spaces, which LINE renders more reliably."""
    width = width or report_width()
    pad_cells = max(0, (width - visual_width(text)) // 2)
    fw = "\u3000" * (pad_cells // 2)
    sp = " " * (pad_cells % 2)
    return fw + sp + text


def divider_line(width: int | None = None) -> str:
    width = width or report_width()
    return "━" * max(8, width // 2)


def pad_right_visual(s: str, width: int) -> str:
    return s + " " * max(0, width - visual_width(s))


def compact_report_source(source: str) -> str:
    if "Actual Rank" in source:
        return "Yahoo AR fallback"
    if "Fantasy Points" in source:
        return "Yahoo Fantasy Points"
    return source


def format_rookie_stats_lines(stats_line: str) -> list[str]:
    """Split prospect stat summaries before LINE's narrow bubble wraps them."""
    if not stats_line:
        return []
    parts = stats_line.split()
    if len(parts) <= 4:
        return [f"    {stats_line}"]

    split_at = 4 if any("HR" in p for p in parts) else 3
    first = " ".join(parts[:split_at])
    rest = " ".join(parts[split_at:])
    if not rest:
        return [f"    {first}"]
    return [f"    {first}", f"    {rest}"]
