"""
Fantasy Baseball Keeper League - League Rules Configuration
5-Man Keep 盟 聯盟規則設定
"""

# ========== League Basic Info ==========
LEAGUE_NAME = "5-Man Keep盟"
TOTAL_TEAMS = 16
SCORING_FORMAT = "H2H 7x7"
HITTING_CATS = ["R", "H", "HR", "RBI", "SB", "AVG", "OPS"]
PITCHING_CATS = ["W", "SV", "HLD", "K", "ERA", "WHIP", "QS"]
MIN_IP = 30  # minimum innings pitched per matchup

# ========== Roster Positions ==========
ROSTER_POSITIONS = {
    "active": ["C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "UT", "UT"],
    "pitchers": ["SP", "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"],
    "bench": ["BN"] * 5,
    "na": ["NA"] * 2,
    "dl": ["DL"] * 4,
}

# ========== Salary Cap ==========
SALARY_BASE = 300          # 2023 base salary cap
SALARY_INCREMENT = 5       # yearly increment starting from 2024
SALARY_START_YEAR = 2024   # year salary increments begin

FAAB_BASE = 100            # yearly FAAB budget
MIN_BID = 1                # minimum FAAB bid / minimum salary


def get_salary_cap(year: int) -> int:
    """Calculate salary cap for a given year.
    2023: $300, 2024: $305, 2025: $310, 2026: $315, ...
    """
    if year < SALARY_START_YEAR:
        return SALARY_BASE
    return SALARY_BASE + (year - SALARY_START_YEAR + 1) * SALARY_INCREMENT


# ========== Playoff Ranking Bonus ==========
RANKING_BONUS = {
    1: 10,  # 1st place: +$10
    2: 7,   # 2nd place: +$7
    3: 5,   # 3rd place: +$5
    4: 3,   # 4th place: +$3
    5: 2,   # 5th place: +$2
    6: 1,   # 6th place: +$1
}

# ========== Keeper Rules ==========
KEEPER_ACTIVE_MIN = 6      # minimum active keepers
KEEPER_ACTIVE_MAX = 10     # maximum active keepers (A/B/N/O contracts)
KEEPER_BENCH_MAX = 2       # maximum R-contract bench keepers
MIN_ROSTER_SIZE = 5        # minimum players on roster at all times

# ========== Contract Types ==========
CONTRACT_TYPES = ["A", "B", "N", "O", "R"]

# Contract flow:
# Draft/FAAB -> A -> B -> O (option year, then FA)
#                     B -> N(x)+O (extension: salary + N*$5)
#                          N(x) -> N(x-1) -> ... -> N1 -> O -> FA
# R (rookie, bench only) -> activate -> A

EXTENSION_COST_PER_YEAR = 5  # salary increases by $5 per extension year (N)

# ========== Buyout Rules ==========
# Normal buyout: salary * remaining_years (paid from salary cap)
# FAAB buyout: pay salary/2 from FAAB each year
#   - If salary is odd, FAAB pays the larger half (ceil)
#   - e.g., $11 -> FAAB pays $6, salary pays $5

# Buyout penalty per missed FAAB pickup (sequential)
FAAB_PENALTY_FIRST = 5
FAAB_PENALTY_SUBSEQUENT = 10  # 2nd: $10, 3rd: $15, etc.

# Players with FAAB >= $10 must become keepers
FAAB_KEEPER_THRESHOLD = 10

# ========== Trade Rules ==========
# When a player is traded with different contract status:
#   - Salary: use the HIGHER salary between original and trade price
#   - Contract: use the LONGER remaining contract
#   - Priority: Extension/O > B > A > R (longest to shortest)
MAX_TRADE_INSTALLMENT_YEARS = 5  # max installment years for salary compensation trades

# ========== Special Clause ==========
# Players who retire, get lifetime ban, domestic violence cases, etc.
# -> No salary payment required, doesn't count toward 10-man keeper limit
# -> Must be noted below team roster
# -> If player returns, original contract resumes or GM can choose buyout

# ========== DL / Injured Reserve ==========
# If 2+ players from same team are on DL, only counts as 1 slot
# Cannot pick up same-team players directly, must go through waiver or trade

# ========== Waiver Rules ==========
# FAAB $0 bids are invalid -> league extends to next position
# Waiver priority: 1st year = current standings, 2nd year = previous season
#   Last place gets 1st priority, descending

# ========== Season Schedule ==========
PLAYOFF_WEEKS = [23, 24, 25]  # week numbers for playoffs
PLAYOFF_TEAMS = 8

# ========== Yahoo API (populated from .env) ==========
YAHOO_LEAGUE_ID = None  # set via environment variable
YAHOO_GAME_KEY = "mlb"

# ========== Manager Name Mapping ==========
# Maps Excel manager names to Yahoo nicknames (for teams that don't auto-match)
# Format: {excel_name: yahoo_nickname}
MANAGER_NAME_MAPPING = {
    "林剛": "小喆",
    "Yu-Che Chang": "Hyper",
    "Issac": "rawstuff",
    "楊善合": "Ｋａｋｕ",
    # 郭子睿(Rangers) is Kaku's old Excel name (2023-2024).
    # In 2025+, Kaku uses "楊善合" in Excel and "Ｋａｋｕ" on Yahoo.
    # Only add this mapping if processing older years:
    # "郭子睿(Rangers)": "Ｋａｋｕ",
    "Tony林芳民": "Tony",
    "Billy WU": "Billy",
    "Eddie Chen": "EDDIE",
    "James Chen": "魚魚",
    "ywchiou": "YWC",
    "Chih-Wei": "wei",
    "Ponpon": "Ponpon",
    "Hank": "叫我寬哥",
}
