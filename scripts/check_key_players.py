"""Check key traded players' contracts in the rebuild output."""
import json
import unicodedata


def strip_accents(s):
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) not in ("Mn",)).lower()


targets = [
    "Jo Adell", "Tyler Locklear", "Jared Jones", "Laureano", "Jhoan Duran",
    "Vladimir Guerrero", "David Peterson", "Berr", "Devin Williams",
    "Nathan Eovaldi", "Nathaniel Lowe", "Matthew Boyd", "Jeff Hoffman",
    "Mookie Betts", "Corey Seager", "Matt Shaw", "Ryan Helsley",
    "Mitch Keller", "Sandy Alcantara", "Matt Strahm", "Ryan Pepiot",
    "Bryan Reynolds", "Royce Lewis", "Ryan Bergert", "Zach Neto",
    "Carlos Estevez", "Lucas Giolito",
]


def main():
    with open("data/2026_contracts_v2.json", encoding="utf-8") as f:
        data = json.load(f)

    print("KEY PLAYERS - CONTRACT DETAILS")
    print("=" * 120)
    fmt = "{:<12s} | {:<30s} | {:<15s} | 2025: {:<12s} | 2026: {:<12s}{}"
    for mgr, team in sorted(data["teams"].items()):
        for p in team["players"]:
            n = strip_accents(p["name"])
            for t in targets:
                if strip_accents(t) in n:
                    src = p.get("source", "?")
                    c25 = p.get("contract_2025", "?")
                    c26 = p.get("contract_2026", "?")
                    orig = p.get("original_team", "")
                    orig_c = p.get("original_contract", "")
                    extra = ""
                    if orig:
                        extra += f" | orig_team={orig}"
                    if orig_c:
                        extra += f" | orig_contract={orig_c}"
                    print(fmt.format(mgr, p["name"], src, c25, c26, extra))
                    break


if __name__ == "__main__":
    main()
