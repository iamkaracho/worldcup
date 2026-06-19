#!/usr/bin/env python3
"""
Hypothesentest: Bringt ein "GOAT"-/Star-Faktor einen Out-of-sample-Gewinn ueber das
aktuelle 5-Variablen-Modell (bip, bevoelkerung, marktwert, fifa, elo)?

Zwei Operationalisierungen werden getestet:
  - topval   : Marktwert des wertvollsten Spielers (Rohqualitaet des Besten), log
  - topshare : Top-Spieler-Wert / Kaderwert (Star-Konzentration / "Ein-Mann-Team")

Idee: Marktwert deckt Starpower meist ab - aber bei alternden GOATs (Messi 39,
Ronaldo 41) ist der Marktwert niedrig, der Einfluss nicht. Traegt ein Star-Signal
also etwas Eigenes? Uebernahme nur bei Log-Loss-Gewinn. Werte ILLUSTRATIV.
Beruehrt keine Hauptdateien. Nur Standardbibliothek.
"""

import calibrate
import model

# Marktwert des wertvollsten Spielers je Team (Mio EUR, ~2026, illustrativ/gerundet)
TOPVAL = {
    "Mexiko": 30, "Suedkorea": 50, "Suedafrika": 8, "Tschechien": 40, "Kanada": 70,
    "Schweiz": 45, "Katar": 8, "Bosnien-Herzegowina": 35, "Brasilien": 180,
    "Marokko": 70, "Schottland": 45, "Haiti": 10, "USA": 70, "Paraguay": 25,
    "Australien": 15, "Tuerkei": 75, "Deutschland": 140, "Ecuador": 80, "Curacao": 5,
    "Elfenbeinkueste": 50, "Niederlande": 80, "Japan": 45, "Tunesien": 12, "Schweden": 120,
    "Belgien": 70, "Aegypten": 40, "Iran": 15, "Neuseeland": 8, "Spanien": 200,
    "Uruguay": 100, "Saudi-Arabien": 10, "Kap Verde": 12, "Frankreich": 170,
    "Norwegen": 180, "Senegal": 65, "Irak": 5, "Argentinien": 90, "Oesterreich": 45,
    "Algerien": 40, "Jordanien": 5, "Portugal": 90, "Kolumbien": 80, "Usbekistan": 10,
    "DR Kongo": 30, "England": 180, "Kroatien": 75, "Ghana": 40, "Panama": 8,
}

BASE_W = dict(model.WEIGHTS)
BASE_LOG = set(model.LOG_VARS)
_ORIG_LOAD = model.load_teams


def loader(extra_name, extra_vals):
    def _load(path):
        t = _ORIG_LOAD(path)
        for k in t:
            t[k][extra_name] = extra_vals[k]
        return t
    return _load


def evaluate(extra_name=None, extra_vals=None, log=False):
    if extra_name:
        model.WEIGHTS = BASE_W | {extra_name: 1.0}
        model.LOG_VARS = BASE_LOG | ({extra_name} if log else set())
        model.load_teams = loader(extra_name, extra_vals)
    else:
        model.WEIGHTS, model.LOG_VARS, model.load_teams = dict(BASE_W), set(BASE_LOG), _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())
    M = calibrate.load_matches()
    train = [m for m in M if m["date"] < calibrate.TEST_FROM]
    test = [m for m in M if m["date"] >= calibrate.TEST_FROM]
    p = calibrate.fit(train, iters=5000)
    return p, calibrate._result_logloss(test, p)


def main():
    teams = _ORIG_LOAD(model.TEAMS_PATH)
    topshare = {k: TOPVAL[k] / float(teams[k]["marktwert"]) for k in teams}

    print("GOAT-/Star-Faktor als 6. Variable — Out-of-sample-Vergleich\n")
    _, ll5 = evaluate()
    p_v, ll_v = evaluate("topval", TOPVAL, log=True)
    p_s, ll_s = evaluate("topshare", topshare, log=False)

    def share(p, name):
        tot = sum(abs(x) for x in p["weights"].values()) or 1.0
        return abs(p["weights"][name]) / tot

    print(f"  5 Variablen (aktuell)        Test-LogLoss: {ll5:.4f}")
    print(f"  + Top-Spieler-Wert (topval)  Test-LogLoss: {ll_v:.4f}   "
          f"(Gewichtsanteil {share(p_v,'topval'):.0%})")
    print(f"  + Star-Konzentration (share) Test-LogLoss: {ll_s:.4f}   "
          f"(Gewichtsanteil {share(p_s,'topshare'):.0%})")

    best = min([("topval", ll_v), ("topshare", ll_s)], key=lambda x: x[1])
    print()
    if best[1] < ll5 - 1e-4:
        print(f"  => '{best[0]}' HILFT ({(ll5-best[1])/ll5*100:+.2f}%) -> aufnehmen lohnt.")
    else:
        print(f"  => kein Gewinn ({(ll5-best[1])/ll5*100:+.2f}%). Der GOAT-Faktor steckt")
        print("     bereits im Marktwert/Elo -> nicht aufnehmen. (Wie erwartet.)")

    model.WEIGHTS, model.LOG_VARS, model.load_teams = dict(BASE_W), set(BASE_LOG), _ORIG_LOAD
    calibrate.VARS = list(model.WEIGHTS.keys())


if __name__ == "__main__":
    main()
