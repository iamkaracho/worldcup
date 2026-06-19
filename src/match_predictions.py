#!/usr/bin/env python3
"""
Spielplan-Prognosen: fuer jedes der 72 Gruppenspiele (echter WM-2026-Spielplan)
die Outcome-Wahrscheinlichkeit (Sieg/Remis/Niederlage) und das wahrscheinlichste
Ergebnis - analytisch aus dem kalibrierten Modell (kein Simulieren).

Schreibt output/group_fixtures.json (fuer das Dashboard) und druckt eine Tabelle.
Nur Standardbibliothek.
"""

import csv
import json
import os
import random
from collections import Counter

import calibrate
import model

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def _verify(scores, fixtures, n=20000):
    """Check: analytische Verteilung == simulierte Haeufigkeit (gegen Rauschen)."""
    f = next((x for x in fixtures if x["home"] == "Brasilien"), fixtures[0])
    h, a = f["home"], f["away"]
    random.seed(model.SEED)
    cnt = Counter()
    for _ in range(n):
        cnt[model.match_goals(h, a)] += 1
    print(f"\nVerifikation: {nice(h)} vs {nice(a)} — analytisch vs. {n:,} Simulationen")
    print(f"  {'Ergebnis':>9}{'analytisch':>12}{'simuliert':>11}")
    for i, j, p in f["dist"]:
        print(f"  {i}:{j:<7}{p:>11.1%}{cnt[(i, j)]/n:>11.1%}")
    print("  -> stimmt ueberein; Simulieren liefert dasselbe, nur mit Rauschen.")


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, modus = model.build_scores(teams)
    team2group = {t: g for g, ms in groups.items() for t in ms}

    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    fixtures = []
    for r in rows:
        if r["date"] < "2026-06-01" or "World Cup" not in r["tournament"]:
            continue
        h, a = calibrate.EN2DE.get(r["home_team"]), calibrate.EN2DE.get(r["away_team"])
        if not h or not a or team2group.get(h) != team2group.get(a):
            continue                                   # nur echte Gruppenspiele
        ph, pd, pa, score, _ = model.match_probs(h, a)
        dist = [[i, j, round(p, 4)] for i, j, p in model.score_distribution(h, a, top=5)]
        fixtures.append({"group": team2group[h], "date": r["date"], "home": h, "away": a,
                         "ph": round(ph, 4), "pd": round(pd, 4), "pa": round(pa, 4),
                         "score": list(score), "dist": dist})
    fixtures.sort(key=lambda f: (f["group"], f["date"]))

    print(f"Spielplan-Prognosen — 72 Gruppenspiele  (Modell: {modus})\n")
    cur = None
    for f in fixtures:
        if f["group"] != cur:
            cur = f["group"]; print(f"\nGruppe {cur}")
        top3 = " · ".join(f"{i}:{j} {p:.0%}" for i, j, p in f["dist"][:3])
        print(f"  {nice(f['home']):>18} {f['ph']:>4.0%}/{f['pd']:>3.0%}/{f['pa']:<4.0%} "
              f"{nice(f['away']):<18}  {top3}")

    _verify(scores, fixtures)

    out = os.path.join(model._HERE, "..", "output", "group_fixtures.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(fixtures, fp, ensure_ascii=False, indent=1)
    print(f"\n{len(fixtures)} Spiele. Lesart: P(Heimsieg) / P(Remis) / P(Auswaerts).")
    print(f"Gespeichert: {os.path.relpath(out, model._HERE)}")


if __name__ == "__main__":
    main()
