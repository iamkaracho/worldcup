#!/usr/bin/env python3
"""
Hypothesentest: Bringt das Kader-Durchschnittsalter (Transfermarkt 'e-Alter') ALS
ZUSAETZLICHE Variable einen Out-of-sample-Gewinn gegenueber dem aktuellen Modell
(bip, bevoelkerung, marktwert, fifa, elo)?

ESPN-Inspiration (Power Ranking): Karrierephase/Alter als weicher Faktor. Wir testen
ihn quantitativ am Harness. Uebernahme nur bei Log-Loss-Gewinn (wie bei Elo).
Beruehrt KEINE Hauptdateien. Nur Standardbibliothek.
"""

import calibrate
import model

# Kader-Durchschnittsalter (Transfermarkt-Screenshot, WM 2026). * = verdeckt/geschaetzt.
ALTER = {
    "Mexiko": 27.9, "Suedkorea": 28.1, "Suedafrika": 26.8, "Tschechien": 27.6,
    "Kanada": 27.1, "Schweiz": 28.3, "Katar": 29.4, "Bosnien-Herzegowina": 26.4,
    "Brasilien": 29.2, "Marokko": 26.4, "Schottland": 29.2, "Haiti": 27.6,
    "USA": 26.5, "Paraguay": 29.0, "Australien": 27.4, "Tuerkei": 27.7,
    "Deutschland": 28.0, "Ecuador": 26.1, "Curacao": 28.0, "Elfenbeinkueste": 25.8,
    "Niederlande": 27.7, "Japan": 27.8, "Tunesien": 26.6, "Schweden": 27.6,
    "Belgien": 27.6, "Aegypten": 29.0, "Iran": 30.4, "Neuseeland": 28.1,
    "Spanien": 26.7, "Uruguay": 27.5, "Saudi-Arabien": 28.5, "Kap Verde": 29.7,
    "Frankreich": 27.0, "Norwegen": 26.8, "Senegal": 27.1, "Irak": 27.2,
    "Argentinien": 29.1, "Oesterreich": 28.6, "Algerien": 26.9, "Jordanien": 28.4,
    "Portugal": 28.0, "Kolumbien": 30.1, "Usbekistan": 28.5, "DR Kongo": 29.1,
    "England": 27.1, "Kroatien": 28.8, "Ghana": 27.0, "Panama": 30.4,
}

BASE_W = dict(model.WEIGHTS)
_ORIG_LOAD = model.load_teams


def _load_with_age(path):
    t = _ORIG_LOAD(path)
    for k in t:
        t[k]["alter"] = ALTER[k]
    return t


def evaluate(with_age):
    model.WEIGHTS = (BASE_W | {"alter": 1.0}) if with_age else dict(BASE_W)
    model.load_teams = _load_with_age if with_age else _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())
    M = calibrate.load_matches()
    train = [m for m in M if m["date"] < calibrate.TEST_FROM]
    test = [m for m in M if m["date"] >= calibrate.TEST_FROM]
    p = calibrate.fit(train, iters=5000)
    return p, calibrate._result_logloss(test, p)


def main():
    print("Kader-Alter als 6. Variable — Out-of-sample-Vergleich (Einzelstaerke)\n")
    p5, ll5 = evaluate(False)
    p6, ll6 = evaluate(True)

    tot = sum(abs(x) for x in p6["weights"].values()) or 1.0
    print("Relative |Gewichte| im 6-Variablen-Modell:")
    for v, w in sorted(p6["weights"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {v:<13} {w:+.3f}   ({abs(w)/tot:4.0%})")

    print(f"\n  5 Variablen (aktuell)   Test-LogLoss: {ll5:.4f}")
    print(f"  6 Variablen (+ Alter)   Test-LogLoss: {ll6:.4f}")
    diff = (ll5 - ll6) / ll5 * 100
    if ll6 < ll5 - 1e-4:
        print(f"  => Alter HILFT ({diff:+.2f}%) -> aufnehmen lohnt.")
    else:
        print(f"  => kein Gewinn ({diff:+.2f}%). Alter ist gegenueber Marktwert/Elo")
        print("     weitgehend redundant -> nicht aufnehmen.")

    model.WEIGHTS = dict(BASE_W)
    model.load_teams = _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())


if __name__ == "__main__":
    main()
