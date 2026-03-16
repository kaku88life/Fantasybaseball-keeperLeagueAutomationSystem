"""Parse raw MLB Pipeline Top 100 Prospects text into JSON format."""
import json
import re

RAW_TEXT = """1
Konnor Griffin
SS/OF
Pittsburgh Pirates
AA
2026196' 3" / 222 lbsRR
2
Kevin McGonigle
SS
Detroit Tigers
AA
2026215' 9" / 187 lbsLR
3
Jesús Made
SS/2B
Milwaukee Brewers
AA
2027186' 1" / 221 lbsSR
4
Leo De Vries
SS
Athletics
AA
2026196' 0" / 183 lbsSR
5
JJ Wetherholt
INF
St. Louis Cardinals
AAA
2026235' 9" / 190 lbsLR
6
Nolan McLean
RHP
New York Mets
MLB
2026246' 2" / 214 lbsRR
7
Sebastian Walcott
SS/3B
Texas Rangers
AA
2027206' 4" / 190 lbsRR
8
Samuel Basallo
C/1B
Baltimore Orioles
MLB
2026216' 4" / 180 lbsLR
9
Colt Emerson
SS
Seattle Mariners
AAA
2026206' 0" / 195 lbsLR
10
Max Clark
OF
Detroit Tigers
AA
2026215' 11" / 205 lbsLL
11
Bubba Chandler
RHP
Pittsburgh Pirates
MLB
2026236' 3" / 206 lbsSR
12
Trey Yesavage
RHP
Toronto Blue Jays
MLB
2026226' 4" / 225 lbsRR
13
Eli Willits
SS
Washington Nationals
A
2028186' 1" / 180 lbsSR
14
Walker Jenkins
OF
Minnesota Twins
AAA
2026216' 3" / 210 lbsLR
15
Josue De Paula
OF
Los Angeles Dodgers
AA
2027206' 3" / 185 lbsLL
16
Carson Benge
OF
New York Mets
AAA
2026236' 1" / 184 lbsLR
17
Thomas White
LHP
Miami Marlins
AAA
2026216' 5" / 240 lbsLL
18
Carter Jensen
C
Kansas City Royals
MLB
2026226' 0" / 210 lbsLR
19
Payton Tolle
LHP
Boston Red Sox
MLB
2026236' 6" / 250 lbsLL
20
Travis Bazzana
2B
Cleveland Guardians
AAA
2026235' 11" / 199 lbsLR
21
Kade Anderson
LHP
Seattle Mariners
ROK
2027216' 2" / 179 lbsLL
22
Sal Stewart
INF
Cincinnati Reds
MLB
2026226' 1" / 224 lbsRR
23
Aidan Miller
SS
Philadelphia Phillies
AAA
2026216' 1" / 205 lbsRR
24
Ethan Holliday
SS
Colorado Rockies
A
2029196' 2" / 210 lbsLR
25
Bryce Eldridge
1B
San Francisco Giants
MLB
2026216' 7" / 240 lbsLR
26
Luis Peña
INF
Milwaukee Brewers
A+
2028195' 11" / 185 lbsRR
27
Zyhir Hope
OF
Los Angeles Dodgers
AA
2027215' 10" / 193 lbsLL
28
Andrew Painter
RHP
Philadelphia Phillies
MLB
2026226' 7" / 215 lbsRR
29
Seth Hernandez
RHP
Pittsburgh Pirates
ROK
2028196' 4" / 190 lbsRR
30
Eduardo Quintero
OF
Los Angeles Dodgers
A+
2028206' 1" / 175 lbsRR
31
Franklin Arias
SS
Boston Red Sox
AA
2027205' 11" / 170 lbsRR
32
George Lombard Jr.
INF
New York Yankees
AA
2027206' 2" / 190 lbsRR
33
Ryan Sloan
RHP
Seattle Mariners
A+
2028206' 5" / 220 lbsRR
34
Liam Doyle
LHP
St. Louis Cardinals
AA
2027216' 2" / 220 lbsRL
35
Bryce Rainer
SS
Detroit Tigers
A
2028206' 3" / 195 lbsLR
36
Braden Montgomery
OF
Chicago White Sox
AA
2026226' 2" / 220 lbsSR
37
Rainiel Rodriguez
C
St. Louis Cardinals
A+
2028195' 10" / 197 lbsRR
38
Alfredo Duno
C
Cincinnati Reds
A
2028206' 2" / 210 lbsRR
39
Robby Snelling
LHP
Miami Marlins
AAA
2026226' 3" / 210 lbsRL
40
Josue Briceño
C/1B
Detroit Tigers
AA
2027216' 4" / 200 lbsLR
41
Jamie Arnold
LHP
Athletics
ROK
2027216' 1" / 188 lbsLL
42
Owen Caissie
OF
Miami Marlins
MLB
2026236' 4" / 190 lbsLR
43
Lazaro Montes
OF
Seattle Mariners
AA
2027216' 5" / 210 lbsLR
44
Josuar Gonzalez
SS
San Francisco Giants
ROK
2029186' 0" / 167 lbsSR
45
JoJo Parker
SS
Toronto Blue Jays
ROK
2029196' 2" / 200 lbsLR
46
Chase DeLauter
OF
Cleveland Guardians
MLB
2026246' 3" / 235 lbsLL
47
Aiva Arquette
SS
Miami Marlins
A+
2028226' 5" / 220 lbsRR
48
Jonah Tong
RHP
New York Mets
AAA
2026226' 1" / 180 lbsRR
49
Noah Schultz
LHP
Chicago White Sox
AAA
2026226' 10" / 240 lbsLL
50
Edward Florentino
OF/1B
Pittsburgh Pirates
A
2028196' 3" / 200 lbsLR
51
Jett Williams
SS/2B/OF
Milwaukee Brewers
AAA
2026225' 7" / 179 lbsRR
52
Kaelen Culpepper
SS
Minnesota Twins
AA
2027235' 10" / 185 lbsRR
53
Justin Crawford
OF
Philadelphia Phillies
AAA
2026226' 2" / 188 lbsLR
54
Travis Sykora
RHP
Washington Nationals
AA
2028216' 6" / 232 lbsRR
55
Moisés Ballesteros
C
Chicago Cubs
MLB
2026225' 8" / 195 lbsLR
56
Connelly Early
LHP
Boston Red Sox
MLB
2026236' 3" / 195 lbsLL
57
Gage Jump
LHP
Athletics
AA
2026226' 0" / 200 lbsLL
58
Jaxon Wiggins
RHP
Chicago Cubs
AAA
2026246' 6" / 225 lbsRR
59
Ryan Waldschmidt
OF
Arizona Diamondbacks
AA
2026236' 0" / 205 lbsRR
60
Mike Sirota
OF
Los Angeles Dodgers
A+
2027226' 2" / 188 lbsRR
61
Caleb Bonemer
SS/3B
Chicago White Sox
A+
2028206' 1" / 195 lbsRR
62
Joe Mack
C
Miami Marlins
AAA
2026236' 0" / 210 lbsLR
63
Carson Williams
SS
Tampa Bay Rays
MLB
2026226' 1" / 180 lbsRR
64
Cooper Pratt
SS
Milwaukee Brewers
AA
2026216' 4" / 210 lbsRR
65
Eduardo Tait
C
Minnesota Twins
A+
2028196' 0" / 175 lbsLR
66
Angel Genao
SS
Cleveland Guardians
AAA
2026215' 11" / 150 lbsSR
67
Michael Arroyo
2B
Seattle Mariners
AA
2026215' 10" / 160 lbsRR
68
Cam Caminiti
LHP
Atlanta Braves
A
2027196' 2" / 195 lbsLL
69
Dylan Beavers
OF
Baltimore Orioles
MLB
2026246' 5" / 206 lbsLR
70
Charlie Condon
1B/OF
Colorado Rockies
AA
2026226' 5" / 216 lbsRR
71
Harry Ford
C
Washington Nationals
MLB
2026235' 10" / 200 lbsRR
72
Hagen Smith
LHP
Chicago White Sox
AA
2026226' 3" / 235 lbsLL
73
Billy Carlson
SS
Chicago White Sox
ROK
2029196' 1" / 185 lbsRR
74
Emmanuel Rodriguez
OF
Minnesota Twins
AAA
2026235' 11" / 210 lbsLL
75
Blake Mitchell
C
Kansas City Royals
A+
2027216' 0" / 202 lbsLR
76
Theo Gillen
OF
Tampa Bay Rays
A
2028206' 2" / 195 lbsLR
77
Arjun Nimmala
SS
Toronto Blue Jays
A+
2028206' 0" / 190 lbsRR
78
Jonny Farmelo
OF
Seattle Mariners
A+
2028216' 1" / 205 lbsLR
79
Carlos Lagrange
RHP
New York Yankees
AA
2026226' 7" / 248 lbsRR
80
Jarlin Susana
RHP
Washington Nationals
AA
2027216' 6" / 235 lbsRR
81
Tyler Bremner
RHP
Los Angeles Angels
ROK
2026216' 2" / 190 lbsRR
82
Elmer Rodríguez
RHP
New York Yankees
AAA
2026226' 3" / 160 lbsLR
83
Steele Hall
SS
Cincinnati Reds
ROK
2029185' 10" / 180 lbsRR
84
Kyson Witherspoon
RHP
Boston Red Sox
ROK
2027216' 2" / 206 lbsRR
85
Brody Hopkins
RHP
Tampa Bay Rays
AA
2026246' 4" / 200 lbsRR
86
Rhett Lowder
RHP
Cincinnati Reds
MLB
2026246' 2" / 200 lbsRR
87
Joshua Báez
OF
St. Louis Cardinals
AAA
2026226' 3" / 220 lbsRR
88
Kruz Schoolcraft
LHP
San Diego Padres
A
2029186' 8" / 229 lbsLL
89
Ralphy Velazquez
1B/OF
Cleveland Guardians
AA
2027206' 1" / 240 lbsLR
90
JR Ritchie
RHP
Atlanta Braves
AAA
2026226' 2" / 185 lbsRR
91
Jurrangelo Cijntje
RHP
St. Louis Cardinals
AA
2026225' 11" / 200 lbsSS
92
Emil Morales
SS
Los Angeles Dodgers
A
2029196' 3" / 191 lbsRR
93
Nate George
OF
Baltimore Orioles
A+
2028196' 0" / 200 lbsRR
94
Dax Kilby
SS
New York Yankees
A
2028196' 2" / 190 lbsLR
95
Parker Messick
LHP
Cleveland Guardians
MLB
2026256' 0" / 225 lbsLL
96
Hunter Barco
LHP
Pittsburgh Pirates
MLB
2026256' 4" / 229 lbsLL
97
A.J. Ewing
OF/2B
New York Mets
AA
2027215' 10" / 160 lbsLR
98
Leo Bernal
C
St. Louis Cardinals
AAA
2027226' 0" / 245 lbsSR
99
Cooper Ingle
C
Cleveland Guardians
AAA
2026245' 8" / 190 lbsLR
100
Brandon Sproat
RHP
Milwaukee Brewers
MLB
2026256' 3" / 205 lbsRR"""

# Team name to abbreviation mapping
TEAM_MAP = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "OAK",
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WAS",
}

# Parse the combined last line: e.g. "2026196' 3" / 222 lbsRR"
# Pattern: [eta 4d][age 2d][height feet]' [height inches]" / [weight] lbs[bats][throws]
DETAIL_RE = re.compile(
    r"^(\d{4})(\d{2})(\d+)' (\d+)\" / (\d+) lbs([RLSB])([RLSB])$"
)


def parse_prospects(raw: str) -> list[dict]:
    lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]

    prospects = []
    i = 0
    while i < len(lines):
        # Line 1: rank (number)
        rank = int(lines[i]); i += 1
        # Line 2: name
        name = lines[i]; i += 1
        # Line 3: position
        position = lines[i]; i += 1
        # Line 4: team full name
        team_full = lines[i]; i += 1
        # Line 5: level (AA/AAA/MLB/A/A+/ROK)
        level = lines[i]; i += 1
        # Line 6: combined detail line
        detail_line = lines[i]; i += 1

        m = DETAIL_RE.match(detail_line)
        if not m:
            print(f"WARNING: Could not parse detail line for #{rank} {name}: {detail_line!r}")
            continue

        eta = m.group(1)
        age = int(m.group(2))
        bats = m.group(6)
        throws = m.group(7)

        mlb_team = TEAM_MAP.get(team_full, team_full)
        if mlb_team == team_full:
            print(f"WARNING: Unknown team for #{rank} {name}: {team_full!r}")

        prospect = {
            "rank": rank,
            "name": name,
            "mlb_team": mlb_team,
            "position": position,
            "age": age,
            "bats": bats,
            "throws": throws,
            "eta": eta,
        }
        prospects.append(prospect)

    return prospects


if __name__ == "__main__":
    prospects = parse_prospects(RAW_TEXT)
    print(f"Parsed {len(prospects)} prospects")

    output = {
        "year": 2026,
        "source": "MLB Pipeline",
        "updated_at": "2026-03-16",
        "prospects": prospects,
    }

    out_path = "data/top_100_prospects.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Written to {out_path}")
    # Verify
    for p in prospects[:5]:
        print(f"  #{p['rank']} {p['name']} ({p['position']}) - {p['mlb_team']}, Age {p['age']}, ETA {p['eta']}, {p['bats']}/{p['throws']}")
    print("  ...")
    for p in prospects[-3:]:
        print(f"  #{p['rank']} {p['name']} ({p['position']}) - {p['mlb_team']}, Age {p['age']}, ETA {p['eta']}, {p['bats']}/{p['throws']}")
