#!/usr/bin/env python3
"""
Voll umfaengliche Spieltag-Vorschau mit dem LIVE-Stand.

Fuer einen Spieltag (Default 2) je Gruppe: jedes Spiel analytisch mit
  - Live-Elo (nach den bisher gespielten Spielen, Form drin),
  - aktiven Sperren (att/def-Malus fuers betroffene Match),
  - Dixon-Coles,
plus daneben die VORTURNIER-Prognose (statisches Modell) -> man sieht die Verschiebung.

Aufruf:  python3 matchday_preview.py [spieltag]   (Default 2)
Nur Standardbibliothek.
"""

import csv
import json
import os
import sys
from collections import defaultdict

import model
import snapshot
import calibrate

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste",
        "Aegypten": "Ägypten", "Oesterreich": "Österreich",
        "Bosnien-Herzegowina": "Bosnien", "Saudi-Arabien": "Saudi-Ar.",
        "Neuseeland": "Neuseel.", "DR Kongo": "DR Kongo", "Usbekistan": "Usbek."}
def nn(t): return NICE.get(t, t)


def wdl_score(scores_setter, a, b, adj=None):
    pw, pd, pl, bs, _ = model.match_probs(a, b, adj=adj)
    return pw, pd, pl, bs


def main():
    md = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    rows = snapshot.merge_manual(list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8"))))
    groups = model.load_groups(model.GROUPS_PATH)
    t2g = {t: g for g, ms in groups.items() for t in ms}
    fixed, ko, n_played, _ = snapshot.played_wc_games(rows, t2g)
    played_pairs = {frozenset(k) for k in fixed}

    fx = json.load(open(os.path.join(model._HERE, "..", "output", "group_fixtures.json"),
                        encoding="utf-8"))
    # je Gruppe chronologisch -> Spieltag = index//2
    bygroup = defaultdict(list)
    for x in sorted(fx, key=lambda r: (r["group"], r["date"])):
        bygroup[x["group"]].append(x)
    target = []
    for g, lst in bygroup.items():
        for i, x in enumerate(lst):
            if i // 2 == md - 1:
                target.append(x)

    # Live-Modell (Elo nach Spieltag 1 + Sperren)
    elo = snapshot.fresh_elo(rows)
    teams = {t: dict(v) for t, v in model.load_teams(model.TEAMS_PATH).items()}
    for t in teams:
        if t in elo:
            teams[t]["elo"] = elo[t]
    model.build_scores(teams)
    susp_pair, _ = model.resolve_suspensions(played=played_pairs)

    # Vorturnier-Modell (statisch, kein Live-Elo, keine Sperre)
    def static_probs(a, b):
        model.build_scores(model.load_teams(model.TEAMS_PATH))
        return model.match_probs(a, b)[:3]

    print(f"SPIELTAG {md} — Live-Vorschau (Elo nach {n_played} Spielen + Sperren)")
    print("=" * 70)
    print("Pfeile: Verschiebung der Favoriten-Siegchance ggü. Vorturnier-Prognose\n")

    for g in sorted(bygroup):
        games = [x for x in target if x["group"] == g]
        if not games:
            continue
        print(f"Gruppe {g}")
        for x in games:
            a, b = x["home"], x["away"]
            adj = susp_pair.get(frozenset((a, b)))
            # Live (build_scores schon mit Live-Elo gesetzt -> aber static_probs hat es
            # ueberschrieben; daher Live-Elo erneut setzen)
            model.build_scores(teams)
            pw, pd, pl, bs = wdl_score(None, a, b, adj)
            sw, sd, sl = static_probs(a, b)
            # Favorit live + Verschiebung
            fav_live = max(pw, pl); fav_static = (sw if pw >= pl else sl)
            d = fav_live - fav_static
            arrow = " ▲" if d > 0.03 else " ▼" if d < -0.03 else ""
            flag = "  ⚠Sperre" if adj else ""
            print(f"   {nn(a):>11} {bs[0]}:{bs[1]} {nn(b):<11}  "
                  f"{pw:>3.0%}/{pd:>3.0%}/{pl:>3.0%}"
                  f"   (Vorturnier {sw:>3.0%}/{sd:>3.0%}/{sl:>3.0%}){arrow}{flag}")
        print()


if __name__ == "__main__":
    main()
