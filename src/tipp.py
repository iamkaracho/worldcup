#!/usr/bin/env python3
"""
Der komplette WM-2026-Tipp aus dem Modell.

A) Chalk-Tipp: modale Gruppenendstaende (haeufigster 4er-Endstand je Gruppe aus
   20k Sims), die 8 wahrscheinlichsten Dritten, Annex-C-Zuordnung — dann der
   K.-o.-Baum Spiel fuer Spiel analytisch entschieden (hoehere Weiterkomm-
   Wahrscheinlichkeit gewinnt), mit wahrscheinlichstem Ergebnis.
B) Varianten: haeufigste Finals + Sieger, Halbfinal-Quoten.
C) Cinderella-Radar: Aussenseiter (ausserhalb Top-10) mit den groessten
   Halbfinal-Chancen; erwartete Zahl Nicht-Top-8 im Halbfinale.
D) Ueberraschungs-Quoten: fruehe K.-o.s der Grossen etc.

Nur Standardbibliothek.
"""

import math
import random
from collections import Counter, defaultdict

import model

N = 20_000
NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste",
        "Aegypten": "Ägypten", "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, _ = model.build_scores(teams)
    team2group = {t: g for g, ms in groups.items() for t in ms}
    top8 = set(sorted(scores, key=scores.get, reverse=True)[:8])
    top10 = set(sorted(scores, key=scores.get, reverse=True)[:10])

    random.seed(model.SEED)
    grank = {L: Counter() for L in groups}
    q3_letters = Counter()
    finals, champs, semis = Counter(), Counter(), Counter()
    best = defaultdict(Counter)
    n_outsider_sf = Counter()
    meet = Counter()          # (DE,FR)-Begegnungen
    de_beats_fr = 0
    SFP = {"Halbfinale", "Finale", "Weltmeister"}
    for _ in range(N):
        go = {}
        champ, reached = model.simulate_tournament(groups, scores, group_out=go)
        for L in groups:
            grank[L][tuple(go[L])] += 1
        for t in go["_q3"]:
            q3_letters[team2group[t]] += 1
        champs[champ] += 1
        for t, r in reached.items():
            best[t][r] += 1
        sf = [t for t, r in reached.items() if r in SFP]
        fin = [t for t, r in reached.items() if r in ("Finale", "Weltmeister")]
        semis[frozenset(sf)] += 1
        finals[(frozenset(fin), champ)] += 1
        n_outsider_sf[sum(1 for t in sf if t not in top8)] += 1
        rd, rf = reached["Deutschland"], reached["Frankreich"]
        ridx = {r: i for i, r in enumerate(model.ROUNDS + ["Weltmeister"])}
        # DE-FR-Achtelfinale: beide erreichen AF, einer scheidet dort aus & der
        # andere kommt weiter -> Naeherung ueber Runden geht nicht exakt; zaehlen
        # wir nur: DE ueberlebt das Achtelfinale
        if ridx.get(rd, 0) >= ridx["Viertelfinale"]:
            de_beats_fr += 1   # hier: P(DE erreicht Viertelfinale)

    rank = {r: i for i, r in enumerate(model.ROUNDS + ["Weltmeister"])}

    def p_at_least(t, rname):
        thr = rank[rname]
        return sum(c for r, c in best[t].items() if rank.get(r, 99) >= thr) / N

    # ---------- A) Chalk: modale Gruppen ----------
    W, R, third = {}, {}, {}
    print("A) DER HAUPTTIPP — wahrscheinlichster Endstand je Gruppe (Modus aus 20k Sims)\n")
    for L in sorted(groups):
        order, cnt = grank[L].most_common(1)[0]
        W[L], R[L], third[L] = order[0], order[1], order[2]
        print(f"  {L}: " + " | ".join(f"{i+1}. {nice(t)}" for i, t in enumerate(order))
              + f"   ({cnt/N:.0%} der Sims exakt so)")
    q8 = {L for L, _ in q3_letters.most_common(8)}
    print(f"\n  Beste 8 Dritte aus: {', '.join(sorted(q8))}"
          f"  ({', '.join(nice(third[L]) for L in sorted(q8))})")
    slot_letter = model.assign_thirds(q8)

    def spec_team(spec):
        kind, val = spec
        return W[val] if kind == "W" else R[val] if kind == "R" else third[slot_letter[val]]

    # ---------- Chalk: K.-o.-Baum analytisch ----------
    def adv(a, b):
        pw, pd, pl, bestsc, _ = model.match_probs(a, b)
        pen_a = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
        return pw + pd * pen_a, bestsc

    winner = {}
    rounds_named = [("SECHZEHNTELFINALE", range(73, 89)), ("ACHTELFINALE", range(89, 97)),
                    ("VIERTELFINALE", range(97, 101)), ("HALBFINALE", (101, 102)),
                    ("FINALE", (104,))]
    print("\n  K.-o.-Baum (Favorit kommt jeweils weiter; Klammer = wahrscheinlichstes Ergebnis):")
    for label, ms in rounds_named:
        print(f"\n  {label}")
        for m in ms:
            if m in model.R32:
                a, b = spec_team(model.R32[m][0]), spec_team(model.R32[m][1])
            else:
                ca, cb = model.TREE[m]
                a, b = winner[ca], winner[cb]
            pa, bestsc = adv(a, b)
            w = a if pa >= 0.5 else b
            winner[m] = w
            pen = " n.E." if bestsc[0] == bestsc[1] else ""
            print(f"    {nice(a)} – {nice(b)}  {bestsc[0]}:{bestsc[1]}{pen}"
                  f"   ► {nice(w)} ({max(pa,1-pa):.0%})")
    print(f"\n  ★ TIPP WELTMEISTER: {nice(winner[104]).upper()}"
          f"  (Gesamt-Titelchance lt. Sim: {champs[winner[104]]/N:.1%})")

    # ---------- B) Varianten ----------
    print("\nB) VARIANTEN — die haeufigsten Endspiele (Anteil aller 20k Sims):")
    for (pair, ch), c in finals.most_common(6):
        p = sorted(pair, key=lambda t: t != ch)
        print(f"    {nice(p[0])} schlaegt {nice(p[1])}   {c/N:.1%}")
    print("\n  Halbfinal-Wahrscheinlichkeiten (Top 10):")
    hf = sorted(scores, key=lambda t: -p_at_least(t, "Halbfinale"))[:10]
    for t in hf:
        print(f"    {nice(t):<14}{p_at_least(t,'Halbfinale'):>6.1%}")

    # ---------- C) Cinderella ----------
    print("\nC) CINDERELLA-RADAR — Aussenseiter (nicht Top-10) nach P(Halbfinale):")
    cind = sorted((t for t in scores if t not in top10),
                  key=lambda t: -p_at_least(t, "Halbfinale"))[:8]
    for t in cind:
        print(f"    {nice(t):<16}HF {p_at_least(t,'Halbfinale'):>5.1%}"
              f"   VF {p_at_least(t,'Viertelfinale'):>5.1%}"
              f"   Titel {champs[t]/N:>5.2%}")
    exp_out = sum(k * c for k, c in n_outsider_sf.items()) / N
    p_ge1 = sum(c for k, c in n_outsider_sf.items() if k >= 1) / N
    p_ge2 = sum(c for k, c in n_outsider_sf.items() if k >= 2) / N
    print(f"\n    Erwartete Nicht-Top-8 im Halbfinale: {exp_out:.1f} von 4"
          f"   |   P(≥1)={p_ge1:.0%}, P(≥2)={p_ge2:.0%}")

    # ---------- D) Ueberraschungen ----------
    print("\nD) UEBERRASCHUNGS-QUOTEN:")
    for t in ("Spanien", "Frankreich", "Argentinien", "England", "Brasilien", "Deutschland"):
        out_early = 1 - p_at_least(t, "Achtelfinale")
        out_pre_qf = 1 - p_at_least(t, "Viertelfinale")
        print(f"    {nice(t):<13} raus vor AF: {out_early:>5.1%}   raus vor VF: {out_pre_qf:>5.1%}")
    print(f"    Deutschland erreicht Viertelfinale (= ueberlebt das mutmassliche"
          f" FR-Achtelfinale): {de_beats_fr/N:.1%}")
    for t in ("USA", "Mexiko", "Kanada", "Niederlande"):
        print(f"    {nice(t):<13} Viertelfinale: {p_at_least(t,'Viertelfinale'):>5.1%}"
              f"   Halbfinale: {p_at_least(t,'Halbfinale'):>5.1%}   Titel: {champs[t]/N:>5.2%}")


if __name__ == "__main__":
    main()
