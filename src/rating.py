#!/usr/bin/env python3
"""
Team-Rating mit Klement-Prior (Tier-1-Verbesserung).

Statt die Staerke nur aus 4 Variablen zu rechnen, wird fuer jedes Team ein latentes
Rating r_i DIREKT aus der Spielhistorie geschaetzt (penalisiertes Poisson-Modell,
Elo-Idee). Klements 4-Variablen-Score dient als Bayes-Prior: datenarme Teams werden
zum Strukturwert gezogen, datenreiche folgen den Ergebnissen.

    log lambda_heim = mu + (r_heim - r_gast) + eta * heimrecht
    log lambda_gast = mu + (r_gast - r_heim)
    Strafterm:  -(rho/2) * sum_i (r_i - beta * s_i)^2     (s_i = struktureller Prior)

Zeit-Downweighting: w = 0.5^(Alter / Halbwertszeit) -> juengere Spiele zaehlen mehr.
Ergebnis -> data/team_ratings.json, das model.py bevorzugt laedt ("rating-basiert").

Validierung waehlt rho per Out-of-sample-Log-Loss und vergleicht mit dem rein
strukturellen Modell. Nur Standardbibliothek.

BEFUND (Stand 2026): Das Rating-Modell schlaegt das Strukturmodell out-of-sample
NICHT (best 1.025 vs. 1.016). Mit steigendem rho konvergiert es monoton zum
Strukturmodell - d.h. Marktwert + FIFA-Punkte sind hier kaum zu uebertreffen.
Das Skript uebernimmt das Rating daher NICHT (schreibt kein team_ratings.json) -
Disziplin gegen Komplexitaet, die sich nicht auszahlt (Klements Lektion).
"""

import csv
import json
import math
import os
from datetime import date

import calibrate
import model

WINDOW_START = "2014-01-01"
HALFLIFE_DAYS = 365 * 2.5
RATINGS_PATH = os.path.join(model._HERE, "..", "data", "team_ratings.json")


# --- Daten -------------------------------------------------------------------

def load_history(ref, until=None, start=WINDOW_START):
    """Alle Spiele [start, until) mit Zeitgewicht relativ zu ref. Namen -> DE-Keys
    fuer unsere 48 (Alias-Merge), sonst Original. ref/until als 'YYYY-MM-DD'."""
    ry, rm, rd = map(int, ref.split("-"))
    refd = date(ry, rm, rd)
    out = []
    with open(calibrate.RESULTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r["date"]
            if d < start or (until and d >= until) or r["home_score"] in ("", "NA"):
                continue
            y, m, dd = map(int, d.split("-"))
            age = (refd - date(y, m, dd)).days
            if age < 0:
                continue
            out.append({
                "h": calibrate.EN2DE.get(r["home_team"], r["home_team"]),
                "a": calibrate.EN2DE.get(r["away_team"], r["away_team"]),
                "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                "hf": 0 if r["neutral"].upper() == "TRUE" else 1,
                "w": 0.5 ** (age / HALFLIFE_DAYS),
            })
    return out


def structural_prior():
    """Klement-Score je DE-Team aus dem STRUKTURELLEN (kalibrierten) Modell.
    use_ratings=False verhindert Zirkularitaet (Ratings nicht als eigenen Prior)."""
    return model.build_scores(model.load_teams(model.TEAMS_PATH), use_ratings=False)[0]


# --- Penalisiertes Poisson-Rating --------------------------------------------

def fit(matches, prior, rho, lr=0.5, iters=1500):
    teams = set()
    for mt in matches:
        teams.add(mt["h"]); teams.add(mt["a"])
    r = {t: 0.0 for t in teams}
    mu, eta, beta = math.log(1.35), 0.2, 1.0
    W = sum(mt["w"] for mt in matches) or 1.0
    prior_teams = [t for t in teams if t in prior]
    sp2 = sum(prior[t] ** 2 for t in prior_teams) or 1.0

    for _ in range(iters):
        gmu = geta = 0.0
        gr = {t: 0.0 for t in teams}
        for mt in matches:
            w = mt["w"]
            d = r[mt["h"]] - r[mt["a"]]
            eh = max(-2.5, min(3.0, mu + d + eta * mt["hf"]))
            ea = max(-2.5, min(3.0, mu - d))
            resh = mt["hg"] - math.exp(eh)
            resa = mt["ag"] - math.exp(ea)
            gmu += w * (resh + resa)
            geta += w * resh * mt["hf"]
            gr[mt["h"]] += w * (resh - resa)
            gr[mt["a"]] += w * (resa - resh)
        mu += lr * gmu / W
        eta += lr * geta / W
        # Proximaler (impliziter) Ridge-Schritt -> stabil fuer jedes rho
        denom = 1.0 + lr * rho
        for t in teams:
            p = beta * prior[t] if t in prior else 0.0
            r[t] = (r[t] + lr * gr[t] / W + lr * rho * p) / denom
        # beta per Kleinste-Quadrate (Rating auf Prior regressiert)
        beta = sum(r[t] * prior[t] for t in prior_teams) / sp2
    return {"mu": mu, "eta": eta, "beta": beta, "ratings": r}


def logloss(test, p):
    tot = 0.0
    for mt in test:
        d = p["ratings"].get(mt["h"], 0.0) - p["ratings"].get(mt["a"], 0.0)
        lh = math.exp(max(-2.5, min(3.0, p["mu"] + d + p["eta"] * mt["hf"])))
        la = math.exp(max(-2.5, min(3.0, p["mu"] - d)))
        ph = pd = pa = 0.0
        for i in range(11):
            pi = math.exp(-lh) * lh ** i / math.factorial(i)
            for j in range(11):
                pj = math.exp(-la) * la ** j / math.factorial(j)
                if i > j:    ph += pi * pj
                elif i == j: pd += pi * pj
                else:        pa += pi * pj
        s = ph + pd + pa or 1.0
        ph, pd, pa = ph / s, pd / s, pa / s
        act = ph if mt["hg"] > mt["ag"] else pd if mt["hg"] == mt["ag"] else pa
        tot += -math.log(max(act, 1e-9))
    return tot / len(test)


# --- Hauptlauf: rho waehlen, validieren, final fitten ------------------------

def main():
    prior = structural_prior()

    # Validierung: nur Teams, fuer die wir auch strukturell vergleichen koennen
    train = load_history(ref=calibrate.TEST_FROM, until=calibrate.TEST_FROM)
    test_all = load_history(ref="2026-06-01", start=calibrate.TEST_FROM)
    test = [m for m in test_all if m["h"] in prior and m["a"] in prior]

    print("Team-Rating + Klement-Prior  |  Auswahl von rho per Out-of-sample-Log-Loss")
    print(f"  Train: {len(train)} Spiele (<{calibrate.TEST_FROM}), "
          f"Test: {len(test)} Spiele (WM-Feld, >= {calibrate.TEST_FROM})\n")
    print(f"  {'rho':>6} | {'Test-LogLoss':>12}   (hohes rho -> naehert sich Strukturmodell)")
    best = None
    for rho in (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0):
        p = fit(train, prior, rho, iters=700)
        ll = logloss(test, p)
        flag = ""
        if best is None or ll < best[1]:
            best = (rho, ll); flag = "  <- bisher beste"
        print(f"  {rho:>6} | {ll:>12.4f}{flag}")
    rho = best[0]

    # Vergleich zum rein strukturellen Modell (gleiche Testspiele)
    cm = calibrate.load_matches()
    struct = calibrate.fit([m for m in cm if m["date"] < calibrate.TEST_FROM])
    struct_ll = calibrate._result_logloss(
        [m for m in cm if m["date"] >= calibrate.TEST_FROM], struct)
    better = best[1] < struct_ll
    print(f"\n  Bestes rho = {rho}  ->  Rating-Modell Test-LogLoss {best[1]:.4f}")
    print(f"  Strukturmodell (nur 4 Variablen)        Test-LogLoss {struct_ll:.4f}")
    print(f"  => {'Rating-Modell BESSER' if better else 'STRUKTURMODELL bleibt besser'} "
          f"({(struct_ll-best[1])/struct_ll*100:+.1f}% Log-Loss)\n")

    if not better:
        print("Entscheidung: Rating-Modell wird NICHT uebernommen (wuerde den")
        print("Out-of-sample-Log-Loss verschlechtern). Das Strukturmodell bleibt aktiv.")
        print("-> kein team_ratings.json geschrieben. (Klements Lektion: Disziplin")
        print("   gegen Komplexitaet, die sich nicht auszahlt.)")
        if os.path.exists(RATINGS_PATH):
            os.remove(RATINGS_PATH)
        return

    # Finaler Fit auf voller Historie (Stand 2026-06-01)
    full = load_history(ref="2026-06-01")
    p = fit(full, prior, rho)
    teams48 = list(model.load_teams(model.TEAMS_PATH).keys())
    missing = [t for t in teams48 if t not in p["ratings"]]
    out = {"mu": p["mu"], "eta": p["eta"], "beta": p["beta"], "rho": rho,
           "halflife_days": HALFLIFE_DAYS,
           "ratings": {t: round(p["ratings"][t], 4) for t in teams48 if t not in missing}}
    if missing:
        print(f"  WARNUNG: ohne Spiele im Fenster: {missing} (kein Rating)")
    with open(RATINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Top-12-Ratings (final):")
    for t, rt in sorted(out["ratings"].items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {t:<20} {rt:+.3f}")
    print(f"\nGespeichert: {os.path.relpath(RATINGS_PATH, model._HERE)}")
    print("model.py laeuft ab jetzt im Modus 'rating-basiert (+Klement-Prior)'.")


if __name__ == "__main__":
    main()
