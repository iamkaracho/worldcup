#!/usr/bin/env python3
"""
Spielt EIN komplettes Turnier aus und zeigt es: Gruppentabellen mit Punkten/Toren,
den kompletten K.-o.-Baum mit Ergebnissen, bis zum Weltmeister.

Das ist EIN moeglicher Verlauf von Millionen. Anderer Verlauf: anderen Seed uebergeben:
    python3 playthrough.py            # Standard-Seed
    python3 playthrough.py 42         # anderes Turnier
Nur Standardbibliothek.
"""

import math
import random
import sys

import model

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 2026

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}
ROUND_NAMES = [(range(73, 89), "SECHZEHNTELFINALE"), (range(89, 97), "ACHTELFINALE"),
               (range(97, 101), "VIERTELFINALE"), (range(101, 103), "HALBFINALE"),
               (range(104, 105), "FINALE")]


def nice(t):
    return NICE.get(t, t)


def play_one(groups, scores):
    W, R, third, tstats, tables = {}, {}, {}, {}, {}
    for letter, members in groups.items():
        ranked, stats, _res = model.play_group(members, scores)
        tables[letter] = (ranked, stats)
        W[letter], R[letter], third[letter] = ranked[0], ranked[1], ranked[2]
        tstats[letter] = stats
    q = set(sorted(groups, key=lambda L: model.third_place_key(third[L], tstats[L]),
                   reverse=True)[:8])
    q_teams = {third[L] for L in q}
    slot = model.assign_thirds(q)

    def spec(s):
        kind, val = s
        return W[val] if kind == "W" else R[val] if kind == "R" else third[slot[val]]

    res, cache = {}, {}

    def resolve(m):
        if m in cache:
            return cache[m]
        if m in model.R32:
            a, b = spec(model.R32[m][0]), spec(model.R32[m][1])
        else:
            ca, cb = model.TREE[m]
            a, b = resolve(ca), resolve(cb)
        ga, gb = model.match_goals(a, b)
        pen = ga == gb
        if pen:
            p = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
            winner = a if random.random() < p else b
        else:
            winner = a if ga > gb else b
        res[m] = (a, b, ga, gb, pen, winner)
        cache[m] = winner
        return winner

    champ = resolve(104)
    return tables, q_teams, res, champ


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, modus = model.build_scores(teams)
    random.seed(SEED)
    tables, q_teams, res, champ = play_one(groups, scores)

    print(f"WM 2026 — ein möglicher Verlauf  (Seed {SEED})")
    print(f"Modell: {modus}\n")
    print("=" * 52)
    print("GRUPPENPHASE")
    print("=" * 52)
    for g in sorted(tables):
        ranked, stats = tables[g]
        print(f"\nGruppe {g}")
        for i, t in enumerate(ranked):
            s = stats[t]
            mark = "✓" if i < 2 else ("✓ (3.)" if t in q_teams else "  (3.)" if i == 2 else "")
            print(f"  {i+1}. {nice(t):<18}{s['pts']:>2} Pkt   "
                  f"{s['gf']:>2}:{s['ga']:<2}  {mark}")

    print("\n" + "=" * 52)
    print("K.-O.-RUNDE")
    print("=" * 52)
    for rng, name in ROUND_NAMES:
        ms = [m for m in rng if m in res]
        if not ms:
            continue
        print(f"\n{name}")
        for m in ms:
            a, b, ga, gb, pen, w = res[m]
            tag = f"  n.E. → {nice(w)}" if pen else ""
            print(f"  {nice(a):>18} {ga}:{gb} {nice(b):<18}{tag}")

    print("\n" + "=" * 52)
    print(f"🏆  WELTMEISTER 2026:  {nice(champ).upper()}")
    print("=" * 52)
    print("\n(Ein einzelner Zufallsverlauf. Anderes Turnier: python3 playthrough.py <zahl>)")


if __name__ == "__main__":
    main()
