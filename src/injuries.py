#!/usr/bin/env python3
"""
Wirkung der bekannten WM-2026-Ausfaelle auf die Prognose.

Zieht die Ausfaelle (data/injuries_2026.json) vom Kader-Marktwert ab (out voll,
doubtful 50%) und vergleicht die Titelwahrscheinlichkeiten MIT und OHNE. Re-Kalibrierung
ist nicht noetig: nur die 2026-Inputs aendern sich, die Koeffizienten bleiben.
Nur Standardbibliothek.
"""

import json
import os
import random
from collections import Counter

import model

N = 8000
NICE = {"Suedkorea": "Südkorea", "Tuerkei": "Türkei", "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def run(teams, groups, apply):
    scores, _ = model.build_scores(teams, apply_injuries=apply)
    random.seed(model.SEED)
    titles, _, _ = model.run(groups, scores, n=N)
    n = sum(titles.values())
    return {t: c / n for t, c in titles.items()}


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    with open(model.INJURIES_PATH, encoding="utf-8") as f:
        inj = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    cuts = model.load_injuries()

    print("WM-2026-Ausfaelle — Wirkung auf die Prognose\n")
    print("Bekannte Ausfaelle (Abzug vom Kader-Marktwert):")
    for t in sorted(inj, key=lambda t: -cuts[t]):
        base = teams[t]["marktwert"]
        names = ", ".join(f"{p['player']}"
                          + ("*" if p.get("status") == "doubtful" else "") for p in inj[t])
        print(f"  {nice(t):<13} -{cuts[t]:>5.0f} Mio  ({base:.0f} → {base-cuts[t]:.0f})   {names}")
    print("  (* = fraglich, zu 50% gewertet)")

    p_off = run(teams, groups, apply=False)
    p_on = run(teams, groups, apply=True)

    print(f"\nTitelwahrscheinlichkeit ohne → mit Ausfaellen  ({N:,} Sims):")
    print(f"  {'Team':<14}{'ohne':>7}{'mit':>7}{'Δ':>8}")
    shown = set()
    for t in sorted(p_on, key=lambda t: -p_on[t])[:12]:
        d = p_on[t] - p_off.get(t, 0)
        arrow = "▲" if d > 0.002 else "▼" if d < -0.002 else " "
        print(f"  {nice(t):<14}{p_off.get(t,0):>6.1%}{p_on[t]:>7.1%}{d:>+7.1%} {arrow}")
        shown.add(t)
    # auch betroffene Teams zeigen, falls aus Top-12 gefallen
    for t in sorted(inj, key=lambda t: p_off.get(t, 0), reverse=True):
        if t not in shown:
            d = p_on.get(t, 0) - p_off.get(t, 0)
            print(f"  {nice(t):<14}{p_off.get(t,0):>6.1%}{p_on.get(t,0):>7.1%}{d:>+7.1%} "
                  + ("▼" if d < -0.002 else " "))

    print("\nElo bleibt unveraendert (ergebnisbasiert); nur der Marktwert-Anteil sinkt.")


if __name__ == "__main__":
    main()
