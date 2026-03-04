"""
Fantasy Baseball Keeper League - Data Normalizer

Handles two different Excel contract formats:
  - 2023 style: single string like "$16/N3", "$1/B", "$11/O"
  - 2024+ style: two separate columns (salary: 16.0, contract_type: "N3")

Also normalizes player names and position codes.
"""
from __future__ import annotations

import re
from typing import Optional

from src.contract.models import Contract, ContractType, SpecialStatus


def parse_contract_string(contract_str: str) -> Optional[Contract]:
    """
    Parse a single-string contract notation (2023 format).

    Examples:
        "$16/N3" -> Contract(N, salary=16, extension_years=3)
        "$1/B"   -> Contract(B, salary=1)
        "$11/O"  -> Contract(O, salary=11)
        "$2/R"   -> Contract(R, salary=2)
        "$1/A"   -> Contract(A, salary=1)

    Args:
        contract_str: String like "$16/N3" or "16/N3"

    Returns:
        Contract object or None if parsing fails
    """
    if not contract_str or not isinstance(contract_str, str):
        return None

    contract_str = contract_str.strip()

    # Pattern: optional $ + number + / + contract type (+ optional number for N)
    pattern = r"\$?(\d+)\s*/\s*([ABNOR])(\d*)"
    match = re.match(pattern, contract_str, re.IGNORECASE)
    if not match:
        return None

    salary = int(match.group(1))
    ct_letter = match.group(2).upper()
    ext_num = match.group(3)

    return _build_contract(salary, ct_letter, ext_num)


def parse_contract_columns(
    salary_value,
    contract_type_str: str,
) -> Optional[Contract]:
    """
    Parse contract from two separate columns (2024+ format).

    Examples:
        (16.0, "N3") -> Contract(N, salary=16, extension_years=3)
        (1.0, "B")   -> Contract(B, salary=1)
        (11.0, "O")  -> Contract(O, salary=11)
        (2.0, "R")   -> Contract(R, salary=2)

    Args:
        salary_value: Numeric salary (int or float)
        contract_type_str: String like "N3", "B", "O", "R", "A"

    Returns:
        Contract object or None if parsing fails
    """
    if salary_value is None or contract_type_str is None:
        return None

    try:
        salary = int(float(salary_value))
    except (ValueError, TypeError):
        return None

    contract_type_str = str(contract_type_str).strip().upper()

    # Extract letter and optional number
    match = re.match(r"([ABNOR])(\d*)", contract_type_str)
    if not match:
        return None

    ct_letter = match.group(1)
    ext_num = match.group(2)

    return _build_contract(salary, ct_letter, ext_num)


def _build_contract(salary: int, ct_letter: str, ext_num: str) -> Contract:
    """Build a Contract from parsed components."""
    contract_type_map = {
        "A": ContractType.A,
        "B": ContractType.B,
        "N": ContractType.N,
        "O": ContractType.O,
        "R": ContractType.R,
    }

    ct = contract_type_map.get(ct_letter, ContractType.A)
    extension_years = int(ext_num) if ext_num else 0

    # N contract must have extension_years > 0
    if ct == ContractType.N and extension_years == 0:
        extension_years = 1  # default to N1 if not specified

    return Contract(
        contract_type=ct,
        salary=salary,
        extension_years=extension_years,
    )


def parse_buyout_string(buyout_str: str) -> Optional[dict]:
    """
    Parse buyout notation from Excel.

    Examples:
        "$11/O-6=5"       -> {salary: 11, contract: "O", faab_cost: 6, salary_cost: 5}
        "$25/N1-13=12"    -> {salary: 25, contract: "N1", faab_cost: 13, salary_cost: 12}
        "25/N1-13=12"     -> same
        "7/O - 4 = 3"     -> {salary: 7, contract: "O", faab_cost: 4, salary_cost: 3}
        "$39/B-20=19"     -> {salary: 39, contract: "B", faab_cost: 20, salary_cost: 19}

    Args:
        buyout_str: String from Excel buyout row

    Returns:
        Dict with parsed components or None
    """
    if not buyout_str or not isinstance(buyout_str, str):
        return None

    buyout_str = buyout_str.strip()

    # Pattern: $?salary/contract - deduction = remainder
    pattern = r"\$?(\d+)\s*/\s*([A-Za-z]\d*)\s*-\s*(\d+)\s*=\s*(\d+)"
    match = re.match(pattern, buyout_str)
    if not match:
        return None

    salary = int(match.group(1))
    contract_str = match.group(2).upper()
    deduction = int(match.group(3))
    remainder = int(match.group(4))

    return {
        "salary": salary,
        "contract": contract_str,
        "original_contract": f"${salary}/{contract_str}",
        "faab_cost": deduction,
        "salary_cost": remainder,
        "total": deduction + remainder,
    }


def normalize_player_name(name: str) -> str:
    """
    Normalize player name for matching across different sources.

    Handles:
    - Leading/trailing whitespace and tabs
    - Accented characters (Suárez -> Suarez for matching)
    - Suffixes like "Jr.", "II", "III"
    - Common abbreviations

    Args:
        name: Raw player name from Excel or Yahoo

    Returns:
        Normalized name string
    """
    if not name or not isinstance(name, str):
        return ""

    name = name.strip()
    # Remove leading tabs
    name = name.lstrip("\t")
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)
    # Remove trailing position markers sometimes found in data
    name = re.sub(r"\s+(Bos|NYY|LAD|LAA|SF|SD|CHC|ATL|HOU|TEX|SEA|TB)\s*$", "", name, flags=re.IGNORECASE)

    return name


def normalize_player_name_for_matching(name: str) -> str:
    """
    Further normalize for fuzzy matching (lowercase, remove accents, etc.).
    """
    import unicodedata
    name = normalize_player_name(name)
    # Remove accents
    nfkd = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return name.lower().strip()


def normalize_position(position_str: str) -> str:
    """
    Normalize position codes.

    Examples:
        "LF,CF,RF" -> "LF,CF,RF"
        "1B/LF" -> "1B,LF"
        "SP,RP" -> "SP,RP"
        "P" -> "P"
        "Util" -> "UT"
    """
    if not position_str or not isinstance(position_str, str):
        return ""

    pos = position_str.strip()
    pos = pos.replace("/", ",").replace("、", ",")
    pos = pos.replace("Util", "UT").replace("util", "UT")

    return pos


def detect_special_status(note: str) -> SpecialStatus:
    """
    Detect special clause status from Excel notes.

    Examples:
        "(Legal issue)" -> LEGAL_ISSUE
        "retired" -> RETIRED
        "" -> NONE
    """
    if not note or not isinstance(note, str):
        return SpecialStatus.NONE

    note_lower = note.lower().strip()

    if "legal" in note_lower or "家暴" in note_lower or "醜聞" in note_lower:
        return SpecialStatus.LEGAL_ISSUE
    if "retire" in note_lower or "退休" in note_lower:
        return SpecialStatus.RETIRED
    if "ban" in note_lower or "禁賽" in note_lower:
        return SpecialStatus.LIFETIME_BAN

    return SpecialStatus.NONE
