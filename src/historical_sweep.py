#!/usr/bin/env python3
"""
Historischer Sweep: das (Elo-)Modell rueckwaerts ueber alle WMs seit 1990.

Pro Turnier - mit Elo-Stand VOR dem Turnier (kein Look-ahead), Tormodell auf den
~2 Jahren davor gefittet:
  - Modell-Favorit (hoechste Titelchance)
  - echter Weltmeister: vorab-Titelchance + Rang
  - Match-Log-Loss gegen die Basisrate (schlaegt das Modell den Zufall in der Aera?)

Nur der Elo-Teil ist historisch verfuegbar (FIFA-Punkte ab 1993, Marktwerte ab ~2000),
deshalb das ergebnisbasierte Elo-Modell - exakt das aus validate.py. Champion-Sim mit
generischem, Elo-gesetztem Baum (ohne Gruppenphase -> Naeherung). Nur Standardbibliothek.
"""

import csv
import math
import random
from collections import Counter

import validate as V

# WM: (Trainingsstart, Turnierstart, Turnierende, echter Weltmeister im Datensatz)
WCS = [
    ("1990", "1988-06-01", "1990-06-08", "1990-07-09", "Germany"),
    ("1994", "1992-06-01", "1994-06-17", "1994-07-18", "Brazil"),
    ("1998", "1996-06-01", "1998-06-10", "1998-07-13", "France"),
    ("2002", "2000-05-01", "2002-05-31", "2002-07-01", "Brazil"),
    ("2006", "2004-06-01", "2006-06-09", "2006-07-10", "Italy"),
    ("2010", "2008-06-01", "2010-06-11", "2010-07-12", "Spain"),
    ("2014", "2012-06-01", "2014-06-12", "2014-07-14", "Germany"),
    ("2018", "2016-06-01", "2018-06-14", "2018-07-16", "France"),
    ("2022", "2020-06-01", "2022-11-20", "2022-12-19", "Argentina"),
]


def seed_order(b):
    order = [1]
    while len(order) < b:
        m = len(order) * 2 + 1
        order = [x for s in order for x in (s, m - s)]
    return order


def champion_probs(parts, elo, mu, s, n=3000):
    seeds = sorted(parts, key=lambda t: elo[t], reverse=True)
    B = 1
    while B < len(seeds):
        B *= 2
    pos = {sd: (seeds[sd - 1] if sd <= len(seeds) else None) for sd in range(1, B + 1)}
    bracket0 = [pos[sd] for sd in seed_order(B)]
    champ = Counter()
    for _ in range(n):
        b = bracket0[:]
        while len(b) > 1:
            nb = []
            for i in range(0, len(b), 2):
                x, y = b[i], b[i + 1]
                nb.append(x if y is None else y if x is None else
                          V._elo_winner(x, y, elo, mu, s))
            b = nb
        champ[b[0]] += 1
    return champ


def main():
    rows = list(csv.DictReader(open(V.calibrate.RESULTS_PATH, encoding="utf-8")))
    random.seed(V.model.SEED)
    print("Historischer Sweep — Elo-Modell rueckwaerts ueber 9 WMs (kein Look-ahead)\n")
    print(f"  {'WM':>5} {'Weltmeister':<14}{'Favorit':<14}{'P(Sieger)':>10}{'Rang':>6}"
          f"{'LogLoss':>9}{'Basis':>8}")
    base_tot = mod_tot = ntot = 0
    hits = 0
    for year, tr, t0, t1, champ in WCS:
        elo = V.compute_elo_until(rows, t0)
        mu, s, _ = V.fit_elo_poisson(V._build(
            [r for r in rows if tr <= r["date"] < t0], elo))
        wc = [r for r in rows if t0 <= r["date"] <= t1
              and r["tournament"] == "FIFA World Cup" and r["home_score"] not in ("", "NA")]
        parts = sorted({t for r in wc for t in (r["home_team"], r["away_team"]) if t in elo})
        test = V._build(wc, elo)
        ll_m = V._wdl_logloss(test, mu, s, 0.0)
        ll_b = V._baseline(test, test)
        base_tot += ll_b * len(test); mod_tot += ll_m * len(test); ntot += len(test)

        cp = champion_probs(parts, elo, mu, s)
        n = sum(cp.values())
        fav = cp.most_common(1)[0][0]
        order = [t for t, _ in cp.most_common()]
        rank = order.index(champ) + 1 if champ in order else 99
        p_ch = cp.get(champ, 0) / n
        if fav == champ:
            hits += 1
        print(f"  {year:>5} {champ:<14}{fav:<14}{p_ch:>9.1%}{rank:>6}"
              f"{ll_m:>9.3f}{ll_b:>8.3f}")

    print(f"\n  Modell-Favorit = echter Sieger: {hits}/9 Turniere")
    print(f"  Match-LogLoss gesamt: Modell {mod_tot/ntot:.3f}  vs  Basis {base_tot/ntot:.3f}")
    print("  (Champion-Sim: generischer Elo-gesetzter Baum ohne Gruppenphase -> Naeherung.)")


if __name__ == "__main__":
    main()
