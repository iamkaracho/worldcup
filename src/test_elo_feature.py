#!/usr/bin/env python3
"""
Hypothesentest: Bringt ein Elo-Rating (eloratings.net-Methode, lokal aus results.csv)
ALS ZUSAETZLICHE 5. Variable einen Out-of-sample-Gewinn gegenueber dem bestehenden
4-Variablen-Modell?

Diszipliniert: nur uebernehmen, wenn der Log-Loss sinkt. Beruehrt KEINE Hauptdateien
(monkeypatcht WEIGHTS/load_teams nur im Test). Nur Standardbibliothek.
"""

import csv

import calibrate
import model
import validate as V

BASE_W = dict(model.WEIGHTS)            # die 4 Original-Variablen
_ORIG_LOAD = model.load_teams

# Aktuelles Elo aus der vollen Spielhistorie (World-Football-Elo, wie eloratings.net)
_rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
_elo = V.compute_elo_until(_rows, "2026-07-01")
DE_ELO = {}
for de, al in calibrate.ALIASES.items():
    vals = [_elo[e] for e in al if e in _elo]
    if vals:
        DE_ELO[de] = max(vals)
_MEAN_ELO = sum(DE_ELO.values()) / len(DE_ELO)


def _load_with_elo(path):
    t = _ORIG_LOAD(path)
    for k in t:
        t[k]["elo"] = DE_ELO.get(k, _MEAN_ELO)
    return t


def evaluate(with_elo):
    model.WEIGHTS = (BASE_W | {"elo": 1.0}) if with_elo else dict(BASE_W)
    model.load_teams = _load_with_elo if with_elo else _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())
    M = calibrate.load_matches()
    train = [m for m in M if m["date"] < calibrate.TEST_FROM]
    test = [m for m in M if m["date"] >= calibrate.TEST_FROM]
    p = calibrate.fit(train, iters=5000)
    return p, calibrate._result_logloss(test, p)


def main():
    print("Elo als 5. Variable — Out-of-sample-Vergleich (Einzelstaerke-Modell)\n")
    p4, ll4 = evaluate(False)
    p5, ll5 = evaluate(True)

    print("Relative |Gewichte| im 5-Variablen-Modell:")
    tot = sum(abs(x) for x in p5["weights"].values()) or 1.0
    for v, w in sorted(p5["weights"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {v:<13} {w:+.3f}   ({abs(w)/tot:4.0%})")

    print(f"\n  4 Variablen (aktuell)   Test-LogLoss: {ll4:.4f}")
    print(f"  5 Variablen (+ Elo)     Test-LogLoss: {ll5:.4f}")
    diff = (ll4 - ll5) / ll4 * 100
    if ll5 < ll4 - 1e-4:
        print(f"  => Elo HILFT ({diff:+.2f}% Log-Loss) -> als Variable aufnehmen lohnt.")
    else:
        print(f"  => kein Gewinn ({diff:+.2f}%). Elo ist gegenueber FIFA-Punkten redundant")
        print("     (r=0.90) -> nicht aufnehmen. Klements Disziplin schlaegt zu.")

    # zuruecksetzen (Hygiene)
    model.WEIGHTS = dict(BASE_W)
    model.load_teams = _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())


if __name__ == "__main__":
    main()
