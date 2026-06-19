#!/usr/bin/env python3
"""
Tail-Kalibrierung: Gibt das Modell echten "Aschenputteln" VORAB eine reale Chance —
oder ~0 (= ueberheblich)?

Fuer ikonische Ueberraschungslaeufe wird die PRE-Turnier-Wahrscheinlichkeit des
tatsaechlichen K.-o.-Laufs berechnet: Elo-Stand vor dem Turnier, Elo-Poisson-Modell
auf den ~2 Jahren davor gefittet (kein Look-ahead). P(Lauf) = Produkt der
P(weiterkommen) ueber die echten K.-o.-Gegner.

Kernfrage: sind diese Wahrscheinlichkeiten klein, aber deutlich > 0? Dann respektiert
das Modell die "odd ones out" (Varianz korrekt). Nur Standardbibliothek.
"""

import csv
import json
import math
import os

import validate as V

DENOM = V.ELO_DENOM

# (Jahr, Turnierstart, Team, erreichte Runde, [K.-o.-Gegner auf dem Weg, real besiegt])
SURPRISES = [
    ("2002", "2002-05-31", "Germany", "Finale",
     ["Paraguay", "United States", "South Korea"]),
    ("2010", "2010-06-11", "Uruguay", "Halbfinale", ["South Korea", "Ghana"]),
    ("2014", "2014-06-12", "Costa Rica", "Viertelfinale", ["Greece"]),
    ("2018", "2018-06-14", "Croatia", "Finale", ["Denmark", "Russia", "England"]),
    ("2022", "2022-11-20", "Morocco", "Halbfinale", ["Spain", "Portugal"]),
]


def _minus_years(date_str, years):
    y, m, d = date_str.split("-")
    return f"{int(y)-years}-{m}-{d}"


def wdl(mu, s, elo_t, elo_o):
    """P(Sieg, Remis, Niederlage) des Teams gegen Gegner, neutral, via Poisson-Gitter."""
    dd = (elo_t - elo_o) / DENOM
    lt, lo = math.exp(mu + s * dd), math.exp(mu - s * dd)
    pw = pdr = pl = 0.0
    for i in range(11):
        pi = math.exp(-lt) * lt ** i / math.factorial(i)
        for j in range(11):
            pj = math.exp(-lo) * lo ** j / math.factorial(j)
            if i > j:    pw += pi * pj
            elif i == j: pdr += pi * pj
            else:        pl += pi * pj
    z = pw + pdr + pl or 1.0
    return pw / z, pdr / z, pl / z


def p_advance(mu, s, elo_t, elo_o):
    """K.-o.: weiterkommen = regulaer gewinnen + Remis*Elfmeter (leichter Skill-Edge)."""
    pw, pdr, _ = wdl(mu, s, elo_t, elo_o)
    p_pen = 1.0 / (1.0 + 10 ** ((elo_o - elo_t) / 400))
    return pw + pdr * p_pen


def main():
    rows = list(csv.DictReader(open(V.calibrate.RESULTS_PATH, encoding="utf-8")))
    print("Tail-Kalibrierung — pre-Turnier-Chance des echten Aschenputtel-Laufs\n")
    print(f"  {'WM':>5} {'Team':<12} {'erreichte':<14} {'P(K.o.-Lauf)':>12}   P je Runde")
    results = []
    for year, t0, team, reached, opps in SURPRISES:
        elo = V.compute_elo_until(rows, t0)
        train = V._build([r for r in rows if _minus_years(t0, 2) <= r["date"] < t0], elo)
        mu, s, _ = V.fit_elo_poisson(train)
        if team not in elo:
            print(f"  {year:>5} {team:<12} (kein Elo) - uebersprungen")
            continue
        ps, p_run = [], 1.0
        for o in opps:
            pa = p_advance(mu, s, elo[team], elo.get(o, 1500))
            ps.append(pa); p_run *= pa
        detail = " · ".join(f"vs {o[:3]} {pa:.0%}" for o, pa in zip(opps, ps))
        print(f"  {year:>5} {team:<12} {reached:<14} {p_run:>11.1%}   {detail}")
        results.append({"year": year, "team": team, "reached": reached,
                        "p_run": round(p_run, 4)})

    with open(os.path.join(V.model._HERE, "..", "output", "cinderella_tail.json"),
              "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n  Lesart: klein, aber klar > 0 -> das Modell gibt Aussenseitern eine echte")
    print("  (seltene) Chance. Es weiss nicht WER, aber es schliesst es nicht aus.")
    print("  Ein 'braves' Chalk-Modell wuerde hier ~0% zeigen und waere ueberheblich.")


if __name__ == "__main__":
    main()
