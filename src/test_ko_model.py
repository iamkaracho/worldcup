#!/usr/bin/env python3
"""
Hypothesentest K.-o.-Modell: (1) Bringt ein VERLAENGERUNGS-Term etwas?
(2) Wie steil ist der Staerke-Effekt im ELFMETERSCHIESSEN wirklich?

Status quo im Modell: P(weiter) = P(Sieg 90') + P(Remis 90') * logistic(Δscores/4).
Kandidat:             90' -> Verlaengerung (Poisson, Rate = f * λ/3) -> Elfmeter
                      mit  P(Elfmetersieg) = logistic(kp * Δlogλ).
Δlogλ = log λ_a - log λ_b ist im Hauptmodell EXAKT scores[a]-scores[b]
(att+def) — der Fit ist also 1:1 uebertragbar. Status quo entspricht kp=0.25, f=0.

Harness: alle K.-o.-Spiele der WMs 1990-2022 (Elo-Poisson je Aera, kein Look-ahead),
Zielgroesse "Heimteam kommt weiter" (Elfmetersieger aus shootouts.csv).
Fit (f, kp) per Grid-MLE auf 1990-2014, Out-of-sample-Check auf 2018+2022.
Nur Standardbibliothek.
"""

import csv
import math
import os
from collections import defaultdict

import model
import validate as V
from historical_brackets import WCS

SHOOTOUTS = os.path.join(model._HERE, "..", "data", "raw", "shootouts.csv")
GRID = 11


def load_ko_games(rows, pens):
    """[(jahr, elo_h, elo_a, hf, hg, ag, heim_kam_weiter)] fuer alle 9 WMs."""
    out = []
    for year, tr, t0, t1, champ, ng in WCS:
        elo = V.compute_elo_until(rows, t0)
        mu, s, h = V.fit_elo_poisson(V._build(
            [r for r in rows if tr <= r["date"] < t0], elo))
        wc = sorted([r for r in rows if t0 <= r["date"] <= t1
                     and r["tournament"] == "FIFA World Cup"
                     and r["home_score"] not in ("", "NA")], key=lambda r: r["date"])
        for r in wc[ng * 6:]:
            ht, at = r["home_team"], r["away_team"]
            if ht not in elo or at not in elo:
                continue
            hg, ag = int(r["home_score"]), int(r["away_score"])
            if hg != ag:
                adv = hg > ag
            else:
                w = pens.get(frozenset((ht, at)))
                if w is None:
                    continue
                adv = (w == ht)
            hf = 0 if r["neutral"].upper() == "TRUE" else 1
            out.append({"year": year, "mu": mu, "s": s, "h": h,
                        "d": (elo[ht] - elo[at]) / V.ELO_DENOM, "hf": hf,
                        "draw120": hg == ag, "adv": adv})
    return out


def _wdl(lh, la):
    pw = pd = pl = 0.0
    ph = [math.exp(-lh) * lh ** i / math.factorial(i) for i in range(GRID)]
    pa = [math.exp(-la) * la ** j / math.factorial(j) for j in range(GRID)]
    for i in range(GRID):
        for j in range(GRID):
            p = ph[i] * pa[j]
            if i > j:    pw += p
            elif i == j: pd += p
            else:        pl += p
    z = pw + pd + pl
    return pw / z, pd / z, pl / z


def p_advance(g, f, kp):
    """P(Heimteam weiter) unter Verlaengerungsfaktor f und Elfmeter-Steilheit kp."""
    lh = math.exp(g["mu"] + g["s"] * g["d"] + g["h"] * g["hf"])
    la = math.exp(g["mu"] - g["s"] * g["d"])
    pw, pd, _ = _wdl(lh, la)
    dloglam = math.log(lh) - math.log(la)
    ppen = 1.0 / (1.0 + math.exp(-kp * dloglam))
    if f <= 0:
        return pw + pd * ppen
    pw_et, pd_et, _ = _wdl(lh * f / 3.0, la * f / 3.0)
    return pw + pd * (pw_et + pd_et * ppen)


def logloss(games, f, kp):
    tot = 0.0
    for g in games:
        p = p_advance(g, f, kp)
        tot -= math.log(max(p if g["adv"] else 1 - p, 1e-12))
    return tot / len(games)


def main():
    rows = list(csv.DictReader(open(V.calibrate.RESULTS_PATH, encoding="utf-8")))
    pens = {}
    with open(SHOOTOUTS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pens[frozenset((r["home_team"], r["away_team"]))] = r["winner"]

    games = load_ko_games(rows, pens)
    train = [g for g in games if g["year"] <= "2014"]
    test = [g for g in games if g["year"] > "2014"]
    print(f"K.-o.-Spiele: {len(games)} gesamt, Train {len(train)} (1990-2014), "
          f"Test {len(test)} (2018+2022)\n")

    # deskriptiv: Elfmeterschiessen — gewinnt der Staerkere?
    p_games = [g for g in games if g["draw120"]]
    fav = sum(1 for g in p_games if (g["d"] > 0) == g["adv"] or g["d"] == 0)
    print(f"Elfmeterschiessen (alle 9 WMs): {len(p_games)} Stueck, "
          f"Elo-Favorit gewann {fav}/{len(p_games)} ({fav/len(p_games):.0%})\n")

    # Grid-MLE auf Train
    best = (None, None, 1e9)
    for fi in [x / 10 for x in range(0, 16)]:
        for ki in [x / 20 for x in range(0, 25)]:
            ll = logloss(train, fi, ki)
            if ll < best[2]:
                best = (fi, ki, ll)
    f_fit, kp_fit, _ = best
    print(f"Grid-MLE (Train): f={f_fit:.1f} (Verlaengerungs-Torrate = f*lambda/3), "
          f"kp={kp_fit:.2f}\n")

    print(f"  {'Variante':<38}{'Train':>8}{'Test':>8}")
    for name, f, kp in [
            ("Status quo  (f=0, kp=0.25)", 0.0, 0.25),
            ("Muenzwurf-Elfer  (f=0, kp=0)", 0.0, 0.0),
            (f"nur Elfer-Fit  (f=0, kp={kp_fit:.2f})", 0.0, kp_fit),
            (f"nur Verlaengerung  (f={f_fit:.1f}, kp=0.25)", f_fit, 0.25),
            (f"voller Fit  (f={f_fit:.1f}, kp={kp_fit:.2f})", f_fit, kp_fit)]:
        print(f"  {name:<38}{logloss(train, f, kp):>8.4f}{logloss(test, f, kp):>8.4f}")


if __name__ == "__main__":
    main()
