#!/usr/bin/env python3
"""
Der komplette Tippzettel: alle 104 WM-2026-Spiele mit konkretem Ergebnis-Tipp.

Tipp-Logik (Kicktipp-optimiert): erst die wahrscheinlichste TENDENZ (Sieg/Remis/
Niederlage) waehlen, dann das wahrscheinlichste Ergebnis INNERHALB dieser Tendenz.
Das schlaegt den nackten Modalwert, weil Tendenzpunkte haeufiger sind als
Exakt-Treffer. K.-o.-Spiele: Tipp = Ergebnis nach 90 Minuten; bei Remis steht
dabei, wer danach weiterkommt (n.E.).

Gruppenspiele in Spielplan-Reihenfolge (echte Daten), K.-o. = Chalk-Baum aus
tipp.py-Logik (modale Gruppenendstaende, Favorit kommt weiter), inkl. Spiel um
Platz 3. Schreibt zusaetzlich output/tippzettel.txt. Nur Standardbibliothek.
"""

import json
import math
import os
import random
from collections import Counter

import model

N = 20_000
NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste",
        "Aegypten": "Ägypten", "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def tip_score(a, b):
    """(ga, gb, p_tendenz, p_exakt): bestes Ergebnis innerhalb der besten Tendenz."""
    pw, pd, pl, _, _ = model.match_probs(a, b)
    dist = model.score_distribution(a, b, top=121)
    tend = max(((pw, 1), (pd, 0), (pl, -1)), key=lambda x: x[0])[1]
    for ga, gb, p in dist:
        if (ga > gb) - (ga < gb) == tend:
            return ga, gb, max(pw, pd, pl), p
    ga, gb, p = dist[0]
    return ga, gb, max(pw, pd, pl), p


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, _ = model.build_scores(teams)

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    # ---------- Gruppenphase: echter Spielplan ----------
    with open(os.path.join(model._HERE, "..", "output", "group_fixtures.json"),
              encoding="utf-8") as f:
        fixtures = json.load(f)
    fixtures.sort(key=lambda x: (x["date"], x["group"]))

    emit("DER KOMPLETTE TIPPZETTEL — WM 2026 (Modellstand 2 Tage vor Anpfiff)")
    emit("=" * 74)
    emit("\nGRUPPENPHASE (72 Spiele, echter Spielplan)")
    cur = None
    for x in fixtures:
        if x["date"] != cur:
            cur = x["date"]
            emit(f"\n  {cur}")
        ga, gb, pt, pe = tip_score(x["home"], x["away"])
        emit(f"    [{x['group']}] {nice(x['home']):<16} – {nice(x['away']):<16} "
             f"{ga}:{gb}   (Tendenz {pt:.0%}, exakt {pe:.0%})")

    # ---------- Chalk-Gruppenendstaende (wie tipp.py) ----------
    random.seed(model.SEED)
    grank = {L: Counter() for L in groups}
    q3 = Counter()
    team2group = {t: g for g, ms in groups.items() for t in ms}
    for _ in range(N):
        go = {}
        model.simulate_tournament(groups, scores, group_out=go)
        for L in groups:
            grank[L][tuple(go[L])] += 1
        for t in go["_q3"]:
            q3[team2group[t]] += 1
    W, R, third = {}, {}, {}
    for L in groups:
        order = grank[L].most_common(1)[0][0]
        W[L], R[L], third[L] = order[0], order[1], order[2]
    slot_letter = model.assign_thirds({L for L, _ in q3.most_common(8)})

    def spec_team(spec):
        kind, val = spec
        return W[val] if kind == "W" else R[val] if kind == "R" else third[slot_letter[val]]

    # ---------- K.-o.: Chalk-Baum, Tipp = 90-Minuten-Ergebnis ----------
    def ko_match(a, b):
        ga, gb, pt, pe = tip_score(a, b)
        pw, pd, pl, _, _ = model.match_probs(a, b)
        pen_a = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
        adv_a = pw + pd * pen_a
        w = a if adv_a >= 0.5 else b
        suffix = f"   ► {nice(w)} n.E." if ga == gb else ""
        return ga, gb, pt, pe, w, max(adv_a, 1 - adv_a), suffix

    winner = {}
    rounds = [("SECHZEHNTELFINALE (28.6.–3.7.)", list(range(73, 89))),
              ("ACHTELFINALE (4.–7.7.)", list(range(89, 97))),
              ("VIERTELFINALE (9.–11.7.)", list(range(97, 101))),
              ("HALBFINALE (14./15.7.)", [101, 102]),
              ("SPIEL UM PLATZ 3 (18.7.)", [103]),
              ("FINALE (19.7., New Jersey)", [104])]
    emit("\n\nK.-o.-PHASE (Chalk-Pfad; Tipp = Ergebnis nach 90 Min.)")
    for label, ms in rounds:
        emit(f"\n  {label}")
        for m in ms:
            if m == 103:
                l1 = next(t for t in tm101 if t != winner[101])
                l2 = next(t for t in tm102 if t != winner[102])
                a, b = l1, l2
            elif m in model.R32:
                a, b = spec_team(model.R32[m][0]), spec_team(model.R32[m][1])
            else:
                ca, cb = model.TREE[m]
                a, b = winner[ca], winner[cb]
            ga, gb, pt, pe, w, padv, suffix = ko_match(a, b)
            winner[m] = w
            if m == 101: tm101 = (a, b)
            if m == 102: tm102 = (a, b)
            emit(f"    {nice(a):<16} – {nice(b):<16} {ga}:{gb}{suffix}"
                 f"   (Tendenz {pt:.0%}, weiter {padv:.0%})")

    emit(f"\n  ★ WELTMEISTER-TIPP: {nice(winner[104]).upper()}")
    emit("\nHinweis: Tipps = wahrscheinlichstes Ergebnis innerhalb der wahrschein-")
    emit("lichsten Tendenz. Bei K.-o.-Remis entscheidet lt. Modell quasi die Muenze.")

    out = os.path.join(model._HERE, "..", "output", "tippzettel.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nGespeichert: output/tippzettel.txt")


if __name__ == "__main__":
    main()
