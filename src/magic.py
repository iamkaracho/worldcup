#!/usr/bin/env python3
"""
Wie viel "Magie" (irreduzible Zufaelligkeit) steckt im Modell?

These: Zufall ist kein fehlender Faktor, sondern bereits einkalibriert - aus 49.000
echten Spielen (Poisson-Streuung + Dixon-Coles). Dieses Skript misst das Niveau:
  (1) Spielebene: wie oft gewinnt ueberhaupt der Favorit? wie planbar ist ein Spiel?
  (2) Turnierebene: Titelchance des Favoriten, Entropie der Titelverteilung.
  (3) Der Skill-Regler: Favoriten-Titelchance je nach Staerke-Spreizung k -
      k=0 reiner Zufall, k=1 kalibrierte Realitaet, gross = deterministisch.
Nur Standardbibliothek.
"""

import csv
import math
import random
from collections import Counter

import calibrate
import model


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    scores, modus = model.build_scores(teams)
    att0, def0 = dict(model._ATT), dict(model._DEF)   # kalibrierte Werte sichern

    # --- (1) Spielebene: ueber die 72 echten Gruppenspiele ---
    team2group = {t: g for g, ms in groups.items() for t in ms}
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    fav_win = draw = upset = predict = nfix = 0.0
    for r in rows:
        if r["date"] < "2026-06-01" or "World Cup" not in r["tournament"]:
            continue
        h, a = calibrate.EN2DE.get(r["home_team"]), calibrate.EN2DE.get(r["away_team"])
        if not h or not a or team2group.get(h) != team2group.get(a):
            continue
        ph, pd, pa, _, _ = model.match_probs(h, a)
        stronger_home = scores[h] >= scores[a]
        fav_win += ph if stronger_home else pa
        upset += pa if stronger_home else ph
        draw += pd
        predict += max(ph, pd, pa)
        nfix += 1
    print(f"Wie viel Magie steckt drin?   (Modell: {modus})\n")
    print("(1) SPIELEBENE — Schnitt ueber die 72 Gruppenspiele")
    print(f"    Favorit gewinnt:        {fav_win/nfix:5.1%}")
    print(f"    Unentschieden:          {draw/nfix:5.1%}")
    print(f"    Aussenseiter gewinnt:   {upset/nfix:5.1%}")
    print(f"    -> Favorit holt NICHT 3 Punkte in {1-fav_win/nfix:.0%} der Spiele.")
    print(f"    Wahrscheinlichster Ausgang tritt im Schnitt nur zu {predict/nfix:.0%} ein.")

    # --- (2) Turnierebene ---
    def run_fav(k, n=4000):
        scale_att = {t: k * att0[t] for t in att0}
        scale_def = {t: k * def0[t] for t in def0}
        model._ATT, model._DEF = scale_att, scale_def
        random.seed(model.SEED)
        titles, _, _ = model.run(groups, scores, n=n)
        return titles

    model._ATT, model._DEF = dict(att0), dict(def0)
    random.seed(model.SEED)
    titles = model.run(groups, scores, n=8000)[0]
    n = sum(titles.values())
    fav = titles.most_common(1)[0]
    H = -sum((c / n) * math.log2(c / n) for c in titles.values() if c)
    print("\n(2) TURNIEREBENE")
    print(f"    Favorit ({fav[0]}) wird Weltmeister:  {fav[1]/n:.1%}")
    print(f"    -> in {1-fav[1]/n:.0%} der Turniere gewinnt jemand anderes.")
    print(f"    Entropie der Titelverteilung: {H:.1f} von max {math.log2(48):.1f} Bit")
    print(f"    (= das Turnier ist zu {H/math.log2(48):.0%} 'offen', nicht entschieden)")

    # --- (3) Skill-Regler ---
    print("\n(3) DER SKILL-REGLER — Favoriten-Titelchance je Staerke-Spreizung k")
    print(f"    {'k':>5}  {'Bedeutung':<26}{'Favorit-Titel':>14}")
    labels = {0.0: "reiner Zufall + Heim", 0.5: "halbe Spreizung",
              1.0: "kalibrierte REALITAET", 2.0: "doppelte Spreizung",
              4.0: "fast deterministisch"}
    for k in (0.0, 0.5, 1.0, 2.0, 4.0):
        t = run_fav(k)
        nn = sum(t.values())
        p = t[fav[0]] / nn
        star = "  <— hier sind wir" if k == 1.0 else ""
        print(f"    {k:>5}  {labels[k]:<26}{p:>13.1%}{star}")

    model._ATT, model._DEF = dict(att0), dict(def0)   # zuruecksetzen
    print("\nFazit: Das kalibrierte Niveau (k=1) liegt VIEL naeher am Zufalls- als am")
    print("deterministischen Ende. Die Magie ist da - exakt so viel wie im echten Fussball.")


if __name__ == "__main__":
    main()
