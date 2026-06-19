#!/usr/bin/env python3
"""
Hypothesentest: Bringt eine MATCH-TYP-Gewichtung (Friendlies < Qualifier < Turnier)
out-of-sample etwas? Idee: Freundschaftsspiele sind verrauscht (Experimente, Rotation),
sollten die Kalibrierung also weniger stark bestimmen als Pflicht-/Turnierspiele.

Mechanik: pro Spiel ein Gewichtsfaktor (zusaetzlich zur Zeit-Halbwertszeit), dann das
gewaehlte att/def+decay-Modell neu fitten und den Ergebnis-Log-Loss auf dem Testset
(ab TEST_FROM) vergleichen. Diszipliniert: nur uebernehmen, wenn der Log-Loss sinkt.
Nur Standardbibliothek.
"""

import csv
import math

import calibrate as C
import model

HALFLIFE = C.HALFLIFE_DAYS

# Turnier-Tiers nach Wichtigkeit (Substring-Match auf die tournament-Spalte).
MAJOR = ("FIFA World Cup", "UEFA Euro", "Copa Am", "African Cup", "AFC Asian Cup",
         "Gold Cup", "CONMEBOL", "Confederations")
QUALI = ("qualification", "Nations League", "qualifier")


def tier(tournament):
    t = tournament
    if "Friendly" in t:
        return "friendly"
    if any(k in t for k in QUALI):
        return "quali"
    if any(k in t for k in MAJOR):
        return "major"
    return "other"          # regionale Cups, kleinere Wettbewerbe


def load_typed():
    """wie calibrate.load_matches, aber zusaetzlich mit Tier je Spiel."""
    teams = model.load_teams(model.TEAMS_PATH)
    feats = model.standardized_features(teams)
    out = []
    with open(C.RESULTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["date"] < C.CUTOFF or r["home_score"] in ("", "NA"):
                continue
            h, a = C.EN2DE.get(r["home_team"]), C.EN2DE.get(r["away_team"])
            if not h or not a:
                continue
            out.append({"date": r["date"], "xh": feats[h], "xa": feats[a],
                        "delta": {v: feats[h][v] - feats[a][v] for v in C.VARS},
                        "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                        "hf": 0 if r["neutral"].upper() == "TRUE" else 1,
                        "tier": tier(r["tournament"])})
    return out


def evaluate(weights, matches):
    """weights: {tier: faktor}. Faltet den Faktor in die Decay-Gewichte, fittet
    att/def+decay neu, liefert Test-Log-Loss."""
    for m in matches:
        m["tw"] = weights.get(m["tier"], 1.0)
    orig = C._decay_weights
    C._decay_weights = lambda ms, hl: [b * m["tw"] for b, m in zip(orig(ms, hl), ms)]
    try:
        train = [m for m in matches if m["date"] < C.TEST_FROM]
        test = [m for m in matches if m["date"] >= C.TEST_FROM]
        p = C.fit_split(train, iters=5000, halflife=HALFLIFE)
        p["rho"] = C.fit_rho(train, p)
        return C._result_logloss(test, p), len(test)
    finally:
        C._decay_weights = orig


def main():
    matches = load_typed()
    from collections import Counter
    dist = Counter(m["tier"] for m in matches)
    print("Spiele je Tier (seit CUTOFF):", dict(dist), "\n")

    base, ntest = evaluate({}, matches)        # alle Faktoren 1.0 = Status quo
    print(f"Status quo (alle Spiele gleich):           Test-LogLoss {base:.4f}  (n={ntest})\n")

    print(f"  {'Schema':<46}{'Test-LogLoss':>13}{'Δ':>9}")
    schemes = [
        ("Friendly x0.7", {"friendly": 0.7}),
        ("Friendly x0.5", {"friendly": 0.5}),
        ("Friendly x0.3", {"friendly": 0.3}),
        ("Friendly x0.0 (ignorieren)", {"friendly": 0.0}),
        ("3-Tier: F0.5/Quali0.8/Major1.2", {"friendly": 0.5, "quali": 0.8, "major": 1.2}),
        ("Major x1.5 (Turnier hoch)", {"major": 1.5}),
    ]
    for name, w in schemes:
        ll, _ = evaluate(w, matches)
        tag = "  <- besser" if ll < base - 1e-4 else ""
        print(f"  {name:<46}{ll:>13.4f}{ll-base:>+9.4f}{tag}")


if __name__ == "__main__":
    main()
