#!/usr/bin/env python3
"""
Voller Turnier-Simulationsbericht: spielt ~N komplette WMs durch (Gruppenphase +
K.-o.) und weist die GRUPPENPHASE aus, die das Hauptmodell sonst nur intern abhandelt.

Pro Gruppe je Team: P(Gruppensieg), P(Platz 2), P(Achtelfinale = Top 2 oder bester
Gruppendritter). Plus kompakte Titel-/Tiefenrunden-Zusammenfassung.

Schreibt output/group_stage_2026.csv. Nur Standardbibliothek.
"""

import csv
import os
import random
import sys
from collections import Counter, defaultdict

import model

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, modus = model.build_scores(teams)
    random.seed(model.SEED)             # reproduzierbar

    pos = defaultdict(lambda: [0, 0, 0, 0])     # team -> [P1,P2,P3,P4]-Zaehler
    q_direct = Counter()                        # als Top-2 qualifiziert
    q_third = Counter()                         # als bester Gruppendritter
    titles = Counter()
    reach_sf = Counter()                        # mind. Halbfinale
    rank = {r: i for i, r in enumerate(model.ROUNDS)}
    sf_thr = rank["Halbfinale"]

    print(f"Simuliere {N:,} komplette Turniere …  (Modus: {modus})")
    for _ in range(N):
        gd = {}
        champ, reached = model.simulate_tournament(groups, scores, group_out=gd)
        q3 = gd.pop("_q3")
        for letter, ranked in gd.items():
            for p, t in enumerate(ranked):
                pos[t][p] += 1
            q_direct[ranked[0]] += 1
            q_direct[ranked[1]] += 1
        for t in q3:
            q_third[t] += 1
        titles[champ] += 1
        for t, r in reached.items():
            if rank[r] >= sf_thr:
                reach_sf[t] += 1

    # --- Gruppen-Report ---
    print("\n" + "=" * 60)
    print("GRUPPENPHASE  (Sieg / Platz 2 / Achtelfinal-Qualifikation)")
    print("=" * 60)
    rows_csv = []
    for g in sorted(groups):
        members = groups[g]
        ranked = sorted(members, key=lambda t: -(q_direct[t] + q_third[t]))
        win = max(members, key=lambda t: pos[t][0])
        print(f"\nGruppe {g}   (Tipp Gruppensieger: {nice(win)} {pos[win][0]/N:.0%})")
        print(f"  {'Team':<16}{'Sieg':>7}{'Platz2':>8}{'Quali':>8}")
        for t in ranked:
            adv = (q_direct[t] + q_third[t]) / N
            print(f"  {nice(t):<16}{pos[t][0]/N:>7.0%}{pos[t][1]/N:>8.0%}{adv:>8.0%}")
            rows_csv.append([g, nice(t), f"{pos[t][0]/N:.3f}", f"{pos[t][1]/N:.3f}",
                             f"{(q_direct[t]+q_third[t])/N:.3f}"])

    # --- Titel-/Tiefenrunden-Zusammenfassung ---
    print("\n" + "=" * 60)
    print(f"K.-O.-PHASE  ({N:,} Turniere)")
    print("=" * 60)
    print(f"\n  {'Team':<16}{'Titel':>7}{'Halbfinale+':>13}")
    for t, _ in titles.most_common(12):
        print(f"  {nice(t):<16}{titles[t]/N:>7.1%}{reach_sf[t]/N:>12.1%}")
    champ = titles.most_common(1)[0][0]
    # erwartete Aussenseiter (ausserhalb Top-8 nach Staerke) im Halbfinale
    top8 = {t for t, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:8]}
    exp_out = sum(reach_sf[t] / N for t in scores if t not in top8) / 1  # 4 HF-Plaetze
    print(f"\n  >>> Häufigster Weltmeister: {nice(champ)} ({titles[champ]/N:.1%})")
    print(f"  >>> Erwartete Außenseiter (außerhalb Top-8) im Halbfinale: "
          f"{exp_out:.2f} von 4")

    out = os.path.join(model._HERE, "..", "output", "group_stage_2026.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["gruppe", "team", "p_sieg", "p_platz2", "p_quali"])
        w.writerows(rows_csv)
    print(f"\nGespeichert: {os.path.relpath(out, model._HERE)}")


if __name__ == "__main__":
    main()
