#!/usr/bin/env python3
"""
Parameter-Unsicherheit per Bootstrap (Tier-3-Verbesserung).

Bisher streut in der Prognose nur der Monte-Carlo-Zufall (Spielausgaenge), nicht
aber die SCHAETZUNSICHERHEIT der kalibrierten Koeffizienten. Hier wird der
Spieldatensatz B-mal mit Zuruecklegen resampled, jeweils neu kalibriert, und je
Parametersatz das Turnier simuliert. Die Streuung der Titelwahrscheinlichkeiten
ueber die B Replikate ist das ehrliche Unsicherheitsband.

So trennt sich Parameter-Unsicherheit (Band) von Monte-Carlo-Rauschen (durch
grosses K je Replikat klein gehalten). Genau Klements Punkt: Unsicherheit zeigen,
nicht verstecken. Nur Standardbibliothek.
"""

import csv
import math
import os
import random

import calibrate
import model

B = 24       # Bootstrap-Replikate
K = 5000     # Simulationen je Replikat
FIT_ITERS = 2500


def quantile(sorted_vals, q):
    idx = max(0, min(len(sorted_vals) - 1, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    inj = model.load_injuries()                          # Ausfaelle konsistent abziehen
    teams = {t: dict(v) for t, v in teams.items()}
    for t, cut in inj.items():
        if t in teams:
            teams[t]["marktwert"] = max(1.0, teams[t]["marktwert"] - cut)
    feats = model.standardized_features(teams)
    matches = calibrate.load_matches()
    calib = model.load_calibration() or {}
    rho = calib.get("rho", 0.0)
    hl = calib.get("halflife") or None
    # gleiche Modellvariante wie die deployte Kalibrierung bootstrappen
    split = "att_weights" in calib
    fitter = calibrate.fit_split if split else calibrate.fit
    random.seed(model.SEED)

    print(f"Bootstrap-Unsicherheit  |  B={B} Replikate x K={K} Sims  |  "
          f"Modell: {calib.get('model','single')}\n")

    per_team = {t: [] for t in teams}
    for b in range(B):
        sample = [random.choice(matches) for _ in matches]
        p = fitter(sample, iters=FIT_ITERS, halflife=hl)
        p["rho"] = rho
        scores = model._apply_calib(p, feats)            # setzt _ATT/_DEF/_MU_EFF/_RHO
        model._HOST_ADV = (p["home"] if model.HOST_BONUS is None else model.HOST_BONUS)
        titles, _, _ = model.run(groups, scores, n=K)
        for t in teams:
            per_team[t].append(titles.get(t, 0) / K)
        print(f"  Replikat {b+1:>2}/{B} fertig", end="\r")
    print(" " * 30, end="\r")

    summ = []
    for t, vals in per_team.items():
        sv = sorted(vals)
        summ.append((t, quantile(sv, 0.5), quantile(sv, 0.05), quantile(sv, 0.95)))
    summ.sort(key=lambda x: -x[1])

    print("P(Weltmeister) mit 90%-Unsicherheitsband (Parameter-Bootstrap)\n")
    print(f"  {'Team':<16}{'Median':>8}{'5%':>8}{'95%':>8}   Band")
    for t, med, lo, hi in summ[:16]:
        bar = "#" * round(60 * med)
        span = f"[{lo:.1%} – {hi:.1%}]"
        print(f"  {t:<16}{med:>8.1%}{lo:>8.1%}{hi:>8.1%}   {span}")

    out = os.path.join(model._HERE, "..", "output", "title_uncertainty.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "p_titel_median", "p_titel_5pct", "p_titel_95pct"])
        for t, med, lo, hi in summ:
            w.writerow([t, f"{med:.4f}", f"{lo:.4f}", f"{hi:.4f}"])
    print(f"\nGespeichert: {os.path.relpath(out, model._HERE)}")
    print("Lesart: das Band zeigt, wie sehr der Tipp allein an der "
          "Kalibrierungs-Stichprobe haengt.")


if __name__ == "__main__":
    main()
