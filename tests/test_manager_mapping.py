"""Guards for the legacy Excel-name -> Yahoo-nickname mapping.

Why this is worth a test: api/routers/auth.py::_match_by_nickname uses this
table to pick a team for a first-time login. A wrong row silently assigns a
manager to SOMEONE ELSE'S team, which then lets them edit that team's keepers.

"楊善合" -> "Ｋａｋｕ" was exactly that bug: Ｋａｋｕ's Excel name is
"郭子睿(Rangers)", while "楊善合" belongs to the manager nicknamed "哈寶好".
"""
from __future__ import annotations

import pytest

from config.settings import MANAGER_NAME_MAPPING

# Verified pairs, taken from scripts/analyze_all_trades.py::YAHOO_MGR_TO_EXCEL,
# which was built against real league data.
VERIFIED_YAHOO_TO_EXCEL = {
    "Ｋａｋｕ": "郭子睿(Rangers)",
    "哈寶好": "楊善合",
    "叫我寬哥": "Hank",
    "EDDIE": "Eddie Chen",
    "wei": "Chih-Wei",
    "Tony": "Tony林芳民",
    "rawstuff": "Issac",
    "Billy": "Billy WU",
    "YWC": "ywchiou",
    "小喆": "Yu-Che Chang",
    "Hyper": "林剛",
    "TIMMY LIU": "TIMMY LIU",
    "謙謙": "Javier",
    "魚魚": "James Chen",
    "Ponpon": "Ponpon",
    "Leo": "Leo",
}


def test_kaku_maps_to_his_own_excel_name():
    """The regression that started this: Ｋａｋｕ is 郭子睿(Rangers), not 楊善合."""
    assert MANAGER_NAME_MAPPING["郭子睿(Rangers)"] == "Ｋａｋｕ"
    assert MANAGER_NAME_MAPPING.get("楊善合") != "Ｋａｋｕ"


def test_yangshanhe_is_a_different_manager():
    assert MANAGER_NAME_MAPPING["楊善合"] == "哈寶好"


def test_nicknames_are_unique():
    """Two Excel names sharing one nickname would make team assignment ambiguous."""
    nicknames = list(MANAGER_NAME_MAPPING.values())
    duplicates = {n for n in nicknames if nicknames.count(n) > 1}
    assert not duplicates, f"nickname collision: {duplicates}"


@pytest.mark.parametrize("yahoo_nick,excel_name", sorted(VERIFIED_YAHOO_TO_EXCEL.items()))
def test_mapping_agrees_with_verified_league_data(yahoo_nick, excel_name):
    assert MANAGER_NAME_MAPPING.get(excel_name) == yahoo_nick, (
        f"{excel_name} should map to {yahoo_nick}, "
        f"got {MANAGER_NAME_MAPPING.get(excel_name)!r}"
    )


def test_mapping_has_no_unknown_entries():
    """Anything not in the verified table is suspect — it was never validated."""
    unknown = set(MANAGER_NAME_MAPPING) - set(VERIFIED_YAHOO_TO_EXCEL.values())
    assert not unknown, f"unverified entries: {unknown}"
