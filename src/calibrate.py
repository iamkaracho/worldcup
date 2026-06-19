#!/usr/bin/env python3
"""
Kalibrierung des WM-2026-Modells per Poisson-Regression (Maximum Likelihood).

Vergleicht vier Modellvarianten und waehlt die out-of-sample beste:
  - single        : eine Staerke je Team   log l_h = mu + (s_h - s_a) + h*hf
  - single+decay  : dto. mit Zeit-Downweighting (Form)            (A.2)
  - att/def       : getrennte Angriff/Abwehr  log l_h = mu + (att_h - def_a) + h*hf  (A.1)
  - att/def+decay : Split + Zeitgewichtung                        (A.1 + A.2)
Danach: Dixon-Coles-rho auf dem gewaehlten Mittelwertmodell. Alles wird nur
uebernommen, wenn es den Out-of-sample-Log-Loss senkt.

Ergebnis -> data/calibrated_params.json (von model.py automatisch geladen).
Daten: data/raw/results.csv (martj42/international_results). Nur Standardbibliothek.
"""

import csv
import json
import math
import os
from datetime import date

import model

VARS = list(model.WEIGHTS.keys())   # feste Reihenfolge der 4 Variablen
RESULTS_PATH = os.path.join(model._HERE, "..", "data", "raw", "results.csv")
CUTOFF = "2018-01-01"
TEST_FROM = "2025-01-01"
HALFLIFE_DAYS = 365 * 3             # Form-Halbwertszeit fuer die Decay-Varianten

ALIASES = {
    "Mexiko": ["Mexico"], "Suedkorea": ["South Korea"], "Suedafrika": ["South Africa"],
    "Tschechien": ["Czechia", "Czech Republic"], "Kanada": ["Canada"],
    "Schweiz": ["Switzerland"], "Katar": ["Qatar"],
    "Bosnien-Herzegowina": ["Bosnia and Herzegovina"], "Brasilien": ["Brazil"],
    "Marokko": ["Morocco"], "Schottland": ["Scotland"], "Haiti": ["Haiti"],
    "USA": ["United States"], "Paraguay": ["Paraguay"], "Australien": ["Australia"],
    "Tuerkei": ["Turkey", "Türkiye"], "Deutschland": ["Germany"], "Ecuador": ["Ecuador"],
    "Curacao": ["Curaçao", "Curacao"], "Elfenbeinkueste": ["Ivory Coast"],
    "Niederlande": ["Netherlands"], "Japan": ["Japan"], "Tunesien": ["Tunisia"],
    "Schweden": ["Sweden"], "Belgien": ["Belgium"], "Aegypten": ["Egypt"],
    "Iran": ["Iran"], "Neuseeland": ["New Zealand"], "Spanien": ["Spain"],
    "Uruguay": ["Uruguay"], "Saudi-Arabien": ["Saudi Arabia"], "Kap Verde": ["Cape Verde"],
    "Frankreich": ["France"], "Norwegen": ["Norway"], "Senegal": ["Senegal"],
    "Irak": ["Iraq"], "Argentinien": ["Argentina"], "Oesterreich": ["Austria"],
    "Algerien": ["Algeria"], "Jordanien": ["Jordan"], "Portugal": ["Portugal"],
    "Kolumbien": ["Colombia"], "Usbekistan": ["Uzbekistan"], "DR Kongo": ["DR Congo"],
    "England": ["England"], "Kroatien": ["Croatia"], "Ghana": ["Ghana"], "Panama": ["Panama"],
}
EN2DE = {en: de for de, al in ALIASES.items() for en in al}


# --- Daten -------------------------------------------------------------------

def load_matches(cutoff=CUTOFF):
    teams = model.load_teams(model.TEAMS_PATH)
    feats = model.standardized_features(teams)
    matches = []
    with open(RESULTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["date"] < cutoff or r["home_score"] in ("", "NA"):
                continue
            h, a = EN2DE.get(r["home_team"]), EN2DE.get(r["away_team"])
            if not h or not a:
                continue
            matches.append({
                "date": r["date"],
                "xh": feats[h], "xa": feats[a],
                "delta": {v: feats[h][v] - feats[a][v] for v in VARS},
                "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                "hf": 0 if r["neutral"].upper() == "TRUE" else 1,
            })
    return matches


def _decay_weights(matches, halflife):
    if not halflife:
        return [1.0] * len(matches)
    ds = [date(*map(int, m["date"].split("-"))) for m in matches]
    ref = max(ds)
    return [0.5 ** ((ref - d).days / halflife) for d in ds]


def _clamp(x):
    return max(-2.0, min(3.0, x))


# --- Mittelwertmodelle (Poisson-MLE per gewichtetem Gradientenaufstieg) -------

def fit(matches, lr=0.1, iters=5000, l2=0.01, halflife=None):
    """Einzelstaerke-Modell. log l_h = mu + sum_v b_v*(x_h-x_a)_v + h*hf."""
    w = _decay_weights(matches, halflife)
    W = sum(w) or 1.0
    mu, h = math.log(1.3), 0.0
    b = {v: 0.0 for v in VARS}
    for _ in range(iters):
        gmu = gh = 0.0
        gb = {v: 0.0 for v in VARS}
        for wk, m in zip(w, matches):
            lin = sum(b[v] * m["delta"][v] for v in VARS)
            rh = wk * (m["hg"] - math.exp(_clamp(mu + lin + h * m["hf"])))
            ra = wk * (m["ag"] - math.exp(_clamp(mu - lin)))
            gmu += rh + ra
            gh += rh * m["hf"]
            for v in VARS:
                gb[v] += (rh - ra) * m["delta"][v]
        mu += lr * gmu / W
        h += lr * (gh / W - l2 * h)
        for v in VARS:
            b[v] += lr * (gb[v] / W - l2 * b[v])
    return {"mu": mu, "weights": b, "home": h, "halflife": halflife or 0}


def fit_split(matches, lr=0.1, iters=5000, l2=0.01, halflife=None):
    """Angriff/Abwehr-Modell. log l_h = mu + (att_h - def_a) + h*hf."""
    w = _decay_weights(matches, halflife)
    W = sum(w) or 1.0
    mu, h = math.log(1.3), 0.0
    att = {v: 0.0 for v in VARS}
    dfe = {v: 0.0 for v in VARS}
    for _ in range(iters):
        gmu = gh = 0.0
        ga = {v: 0.0 for v in VARS}
        gd = {v: 0.0 for v in VARS}
        for wk, m in zip(w, matches):
            xh, xa = m["xh"], m["xa"]
            Ah = sum(att[v] * xh[v] for v in VARS)
            Da = sum(dfe[v] * xa[v] for v in VARS)
            Aa = sum(att[v] * xa[v] for v in VARS)
            Dh = sum(dfe[v] * xh[v] for v in VARS)
            rh = wk * (m["hg"] - math.exp(_clamp(mu + (Ah - Da) + h * m["hf"])))
            ra = wk * (m["ag"] - math.exp(_clamp(mu + (Aa - Dh))))
            gmu += rh + ra
            gh += rh * m["hf"]
            for v in VARS:
                ga[v] += rh * xh[v] + ra * xa[v]
                gd[v] += -rh * xa[v] - ra * xh[v]
        mu += lr * gmu / W
        h += lr * (gh / W - l2 * h)
        for v in VARS:
            att[v] += lr * (ga[v] / W - l2 * att[v])
            dfe[v] += lr * (gd[v] / W - l2 * dfe[v])
    return {"mu": mu, "att_weights": att, "def_weights": dfe, "home": h,
            "halflife": halflife or 0}


# --- Vorhersage / Bewertung --------------------------------------------------

def lambdas(p, m):
    """(lambda_heim, lambda_gast) fuer ein Match unter Parametern p (single oder split)."""
    if "att_weights" in p:
        Ah = sum(p["att_weights"][v] * m["xh"][v] for v in VARS)
        Da = sum(p["def_weights"][v] * m["xa"][v] for v in VARS)
        Aa = sum(p["att_weights"][v] * m["xa"][v] for v in VARS)
        Dh = sum(p["def_weights"][v] * m["xh"][v] for v in VARS)
        return (math.exp(p["mu"] + (Ah - Da) + p["home"] * m["hf"]),
                math.exp(p["mu"] + (Aa - Dh)))
    lin = sum(p["weights"][v] * m["delta"][v] for v in VARS)
    return math.exp(p["mu"] + lin + p["home"] * m["hf"]), math.exp(p["mu"] - lin)


def dc_tau(i, j, lh, la, rho):
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def outcome_probs(p, m):
    """P(Heimsieg, Remis, Auswaerts) via (DC-korrigiertem) Poisson-Gitter."""
    lh, la = lambdas(p, m)
    rho = p.get("rho", 0.0)
    ph = pd = pa = 0.0
    for i in range(11):
        pi = math.exp(-lh) * lh ** i / math.factorial(i)
        for j in range(11):
            pj = math.exp(-la) * la ** j / math.factorial(j)
            cell = pi * pj * dc_tau(i, j, lh, la, rho)
            if i > j:    ph += cell
            elif i == j: pd += cell
            else:        pa += cell
    s = ph + pd + pa or 1.0
    return ph / s, pd / s, pa / s


def fit_rho(matches, p):
    """1-D-MLE von rho bei festen Mittelwert-Parametern."""
    pre = [(*lambdas(p, m), m["hg"], m["ag"]) for m in matches]

    def loglik(rho):
        tot = 0.0
        for lh, la, hg, ag in pre:
            z = (math.exp(-lh) * math.exp(-la) * (dc_tau(0, 0, lh, la, rho) - 1)
                 + math.exp(-lh) * la * math.exp(-la) * (dc_tau(0, 1, lh, la, rho) - 1)
                 + lh * math.exp(-lh) * math.exp(-la) * (dc_tau(1, 0, lh, la, rho) - 1)
                 + lh * math.exp(-lh) * la * math.exp(-la) * (dc_tau(1, 1, lh, la, rho) - 1))
            tot += (math.log(max(dc_tau(hg, ag, lh, la, rho), 1e-9))
                    - math.log(max(1 + z, 1e-9)))
        return tot

    best, rho = (0.0, loglik(0.0)), -0.25
    while rho <= 0.0501:
        ll = loglik(rho)
        if ll > best[1]:
            best = (rho, ll)
        rho += 0.005
    return best[0]


def _result_logloss(matches, p):
    tot = 0.0
    for m in matches:
        ph, pd, pa = outcome_probs(p, m)
        actual = ph if m["hg"] > m["ag"] else (pd if m["hg"] == m["ag"] else pa)
        tot += -math.log(max(actual, 1e-9))
    return tot / len(matches)


def _baseline_logloss(train, test):
    c = {"h": 0, "d": 0, "a": 0}
    for m in train:
        c["h" if m["hg"] > m["ag"] else "d" if m["hg"] == m["ag"] else "a"] += 1
    n = sum(c.values())
    pr = {k: max(v / n, 1e-9) for k, v in c.items()}
    return sum(-math.log(pr["h" if m["hg"] > m["ag"] else
                         "d" if m["hg"] == m["ag"] else "a"]) for m in test) / len(test)


# --- Hauptlauf: Modellauswahl, Dixon-Coles, finaler Fit ----------------------

CONFIGS = [
    ("single",        lambda M: fit(M, iters=5000)),
    ("single+decay",  lambda M: fit(M, iters=5000, halflife=HALFLIFE_DAYS)),
    ("att/def",       lambda M: fit_split(M, iters=5000)),
    ("att/def+decay", lambda M: fit_split(M, iters=5000, halflife=HALFLIFE_DAYS)),
]


def main():
    matches = load_matches()
    train = [m for m in matches if m["date"] < TEST_FROM]
    test = [m for m in matches if m["date"] >= TEST_FROM]
    base = _baseline_logloss(train, test)
    print(f"Poisson-Kalibrierung  |  {len(matches)} Spiele ab {CUTOFF} "
          f"(Test: {len(test)} ab {TEST_FROM}, Basis-LogLoss {base:.4f})\n")

    print(f"  {'Variante':<16}{'Test-LogLoss':>12}")
    results = {}
    best = None
    for name, fitter in CONFIGS:
        p = fitter(train)
        ll = _result_logloss(test, p)
        results[name] = (p, ll)
        flag = ""
        if best is None or ll < results[best][1]:
            best = name; flag = "  <- beste"
        print(f"  {name:<16}{ll:>12.4f}{flag}")
    chosen_name = best
    pv = results[chosen_name][0]
    ll_model = results[chosen_name][1]

    # Dixon-Coles auf dem gewaehlten Modell
    rho = fit_rho(train, pv)
    pv_dc = dict(pv); pv_dc["rho"] = rho
    ll_dc = _result_logloss(test, pv_dc)
    dc_better = ll_dc < ll_model
    print(f"\nGewaehlt: '{chosen_name}'  (LogLoss {ll_model:.4f})")
    print(f"Dixon-Coles rho={rho:+.3f}: LogLoss {ll_dc:.4f} "
          f"({'uebernommen' if dc_better else 'kein Gewinn -> rho=0'})")

    # Finaler Fit der gewaehlten Variante auf allen Daten
    final_fitter = dict(CONFIGS)[chosen_name]
    p = final_fitter(matches)
    p["rho"] = fit_rho(matches, p) if dc_better else 0.0
    p["model"] = chosen_name
    p["n_matches"], p["cutoff"], p["fitted_on"] = len(matches), CUTOFF, "results.csv"

    print(f"\nKoeffizienten ({chosen_name}):")
    if "att_weights" in p:
        for v in VARS:
            print(f"  att[{v:<13}]={p['att_weights'][v]:+.3f}   "
                  f"def[{v:<13}]={p['def_weights'][v]:+.3f}")
    else:
        for v in VARS:
            print(f"  b[{v:<13}] = {p['weights'][v]:+.3f}")
    print(f"  Heimvorteil h = {p['home']:+.3f} (~{math.exp(p['home']):.2f}x Tore) | "
          f"MU = {math.exp(p['mu']):.2f}")

    with open(model.CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    print(f"\nGespeichert: {os.path.relpath(model.CALIB_PATH, model._HERE)}")


if __name__ == "__main__":
    main()
