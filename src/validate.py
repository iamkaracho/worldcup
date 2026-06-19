#!/usr/bin/env python3
"""
Validierung des Modells - schliesst zwei Plan-Luecken:

(Gap 2) Reliabilitaetsdiagramm: Wenn das Modell "30%" sagt, passiert es auch in
        ~30%? Geprueft auf den Out-of-sample-Spielen (2025+) mit den kalibrierten
        Parametern.

(Gap 3) Historischer Backtest gegen WM 2014/2018/2022: Fuer jedes Turnier wird ein
        ZEITKORREKTES Staerkesignal (Elo, nur aus Spielen VOR dem Turnier) gebildet,
        ein Poisson-Tormodell auf dem Vorlauf gefittet und auf den Turnierspielen
        getestet (Log-Loss vs. Basisrate). Validiert die Modellform (Staerke ->
        Poisson -> Ergebnis) ueber mehrere Turniere ohne Look-ahead-Bias.

Hinweis: Der Backtest nutzt Elo statt der 4 Klement-Variablen, weil deren
HISTORISCHE Werte (Marktwerte etc.) nicht vorliegen - Elo ist aus results.csv
vollstaendig und zeitkorrekt rekonstruierbar.
"""

import csv
import math
import random
from collections import Counter

import calibrate
import model


# ============================ Gap 2: Reliabilitaet ===========================

def reliability(n_bins=10):
    matches = calibrate.load_matches()
    test = [m for m in matches if m["date"] >= calibrate.TEST_FROM]
    p = calibrate.fit([m for m in matches if m["date"] < calibrate.TEST_FROM])

    # Sammle (vorhergesagte P, eingetreten?) ueber ALLE drei Ausgaenge je Spiel
    pts = []
    for m in test:
        ph, pd, pa = calibrate.outcome_probs(p, m)
        res = "h" if m["hg"] > m["ag"] else "d" if m["hg"] == m["ag"] else "a"
        pts.append((ph, res == "h"))
        pts.append((pd, res == "d"))
        pts.append((pa, res == "a"))

    bins = [[] for _ in range(n_bins)]
    for prob, hit in pts:
        bins[min(n_bins - 1, int(prob * n_bins))].append((prob, hit))

    print(f"Gap 2 - Reliabilitaet ({len(test)} Out-of-sample-Spiele, "
          f"{len(pts)} Ausgangs-Wahrscheinlichkeiten)\n")
    print(f"  {'Bin':>11} | {'vorhergesagt':>12} | {'beobachtet':>10} | {'n':>4}")
    ece = 0.0
    for i, b in enumerate(bins):
        if not b:
            continue
        pred = sum(p for p, _ in b) / len(b)
        obs = sum(1 for _, h in b if h) / len(b)
        ece += len(b) / len(pts) * abs(pred - obs)
        flag = "" if abs(pred - obs) < 0.08 else "  <- Abweichung"
        print(f"  {i/n_bins:.1f}-{(i+1)/n_bins:.1f} | {pred:>11.1%} | "
              f"{obs:>10.1%} | {len(b):>4}{flag}")
    print(f"\n  Expected Calibration Error (ECE): {ece:.3f}  "
          f"({'gut kalibriert' if ece < 0.05 else 'leichte Fehlkalibrierung'})")


# ============================ Gap 3: Elo-Backtest ============================

def compute_elo_until(rows, until_date, k=40, ha=65):
    """Standard-Elo aus allen Spielen vor until_date. Gibt {team: rating}."""
    elo = {}
    for r in rows:
        if r["date"] >= until_date or r["home_score"] in ("", "NA"):
            continue
        h, a = r["home_team"], r["away_team"]
        rh = elo.get(h, 1500.0)
        ra = elo.get(a, 1500.0)
        adv = 0 if r["neutral"].upper() == "TRUE" else ha
        eh = 1.0 / (1.0 + 10 ** (-((rh + adv) - ra) / 400))
        hg, ag = int(r["home_score"]), int(r["away_score"])
        sh = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        # Tordifferenz-Gewicht (WM-uebliche Variante)
        g = max(1, abs(hg - ag))
        mult = math.sqrt(g)
        elo[h] = rh + k * mult * (sh - eh)
        elo[a] = ra + k * mult * ((1 - sh) - (1 - eh))
    return elo


ELO_DENOM = 400.0  # natuerliche Elo-Skala -> zahme Gradienten


def fit_elo_poisson(train, lr=0.3, iters=6000, l2=0.001):
    """log lam_i = mu + s*(elo_i - elo_j)/400 + h*hf ; Poisson-MLE (konkav)."""
    mu, s, h = math.log(1.35), 0.0, 0.0
    n = len(train)
    for _ in range(iters):
        gmu = gs = gh = 0.0
        for m in train:
            d = m["elo_diff"] / ELO_DENOM
            eh = max(-2.0, min(3.0, mu + s * d + h * m["hf"]))
            ea = max(-2.0, min(3.0, mu - s * d))
            rh = m["hg"] - math.exp(eh)
            ra = m["ag"] - math.exp(ea)
            gmu += rh + ra
            gs += (rh - ra) * d
            gh += rh * m["hf"]
        mu += lr * gmu / n
        s += lr * (gs / n - l2 * s)
        h += lr * (gh / n - l2 * h)
    return mu, s, h


def _wdl_logloss(test, mu, s, h):
    tot = 0.0
    for m in test:
        d = m["elo_diff"] / ELO_DENOM
        lh = math.exp(mu + s * d + h * m["hf"])
        la = math.exp(mu - s * d)
        ph = pd = pa = 0.0
        for i in range(11):
            pi = math.exp(-lh) * lh ** i / math.factorial(i)
            for j in range(11):
                pj = math.exp(-la) * la ** j / math.factorial(j)
                if i > j:    ph += pi * pj
                elif i == j: pd += pi * pj
                else:        pa += pi * pj
        s2 = ph + pd + pa or 1.0
        ph, pd, pa = ph / s2, pd / s2, pa / s2
        act = ph if m["hg"] > m["ag"] else pd if m["hg"] == m["ag"] else pa
        tot += -math.log(max(act, 1e-9))
    return tot / len(test)


def _baseline(train, test):
    c = {"h": 0, "d": 0, "a": 0}
    for m in train:
        c["h" if m["hg"] > m["ag"] else "d" if m["hg"] == m["ag"] else "a"] += 1
    n = sum(c.values())
    pr = {x: max(v / n, 1e-9) for x, v in c.items()}
    return sum(-math.log(pr["h" if m["hg"] > m["ag"] else
                         "d" if m["hg"] == m["ag"] else "a"]) for m in test) / len(test)


WORLD_CUPS = {  # (Trainingsfenster-Start, Turnierstart, Turnierende)
    "2014": ("2012-06-01", "2014-06-12", "2014-07-14"),
    "2018": ("2016-06-01", "2018-06-14", "2018-07-16"),
    "2022": ("2020-06-01", "2022-11-20", "2022-12-19"),
}


def historical_backtest():
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    print("Gap 3 - Historischer Backtest (Elo, zeitkorrekt, kein Look-ahead)\n")
    print(f"  {'WM':>5} | {'Spiele':>6} | {'LogLoss Modell':>14} | "
          f"{'LogLoss Basis':>13} | Urteil")
    for year, (tr_start, t0, t1) in WORLD_CUPS.items():
        elo = compute_elo_until(rows, t0)

        def make(sub):
            out = []
            for r in sub:
                h, a = r["home_team"], r["away_team"]
                if h not in elo or a not in elo or r["home_score"] in ("", "NA"):
                    continue
                out.append({"elo_diff": elo[h] - elo[a],
                            "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                            "hf": 0 if r["neutral"].upper() == "TRUE" else 1})
            return out

        train = make([r for r in rows if tr_start <= r["date"] < t0])
        test = make([r for r in rows if t0 <= r["date"] <= t1
                     and r["tournament"] == "FIFA World Cup"])
        mu, s, h = fit_elo_poisson(train)
        ll_m = _wdl_logloss(test, mu, s, h)
        ll_b = _baseline(train, test)
        verdict = "Modell besser" if ll_m < ll_b else "kein Gewinn"
        print(f"  {year:>5} | {len(test):>6} | {ll_m:>14.4f} | {ll_b:>13.4f} | {verdict}")
    print("\n  Interpretation: schlaegt das Modell ueber alle drei Turniere die")
    print("  Basisrate, generalisiert die Form (Staerke->Poisson->Ergebnis).")


# ===================== Gap B: Champion-Level-Backtest =======================

# Standard-Setzliste 32 (Favoriten treffen erst spaet) - generischer K.-o.-Baum.
SEED_ORDER_32 = [1, 32, 16, 17, 8, 25, 9, 24, 4, 29, 13, 20, 5, 28, 12, 21,
                 2, 31, 15, 18, 7, 26, 10, 23, 3, 30, 14, 19, 6, 27, 11, 22]
CHAMPIONS = {"2014": "Germany", "2018": "France", "2022": "Argentina"}


def _build(sub, elo):
    out = []
    for r in sub:
        h, a = r["home_team"], r["away_team"]
        if h in elo and a in elo and r["home_score"] not in ("", "NA"):
            out.append({"elo_diff": elo[h] - elo[a],
                        "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                        "hf": 0 if r["neutral"].upper() == "TRUE" else 1})
    return out


def _elo_winner(a, b, elo, mu, s):
    d = (elo[a] - elo[b]) / ELO_DENOM
    ga, gb = model._poisson(math.exp(mu + s * d)), model._poisson(math.exp(mu - s * d))
    if ga != gb:
        return a if ga > gb else b
    return a if random.random() < 1 / (1 + 10 ** ((elo[b] - elo[a]) / 400)) else b


def champion_backtest(n=4000):
    """Sanity-Check auf Turnier-Ebene: gab das Modell den echten Weltmeistern
    vernuenftige Titelchancen? Vereinfachter 32er-K.-o.-Baum (Elo-gesetzt, ohne
    Gruppenphase) -> Naeherung; bei nur 3 Turnieren v.a. eine Plausibilitaetspruefung."""
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    random.seed(model.SEED)
    print("Gap B - Champion-Level-Backtest (Titelchance des echten Siegers)\n")
    print(f"  {'WM':>5} | {'Sieger':>11} | {'P(Titel) Modell':>16} | {'Rang':>5} | Top-Tipp")
    ign = []
    for year, (_, t0, t1) in WORLD_CUPS.items():
        elo = compute_elo_until(rows, t0)
        tr_start = WORLD_CUPS[year][0]   # Trainingsfenster wie im historischen Backtest
        mu, s, _ = fit_elo_poisson(_build(
            [r for r in rows if tr_start <= r["date"] < t0], elo))
        parts = set()
        for r in rows:
            if (t0 <= r["date"] <= t1 and r["tournament"] == "FIFA World Cup"
                    and r["home_score"] not in ("", "NA")):
                parts.update((r["home_team"], r["away_team"]))
        seeds = sorted((p for p in parts if p in elo), key=lambda t: elo[t],
                       reverse=True)[:32]
        if len(seeds) < 32:
            print(f"  {year:>5} | nur {len(seeds)} Teilnehmer mit Elo - uebersprungen")
            continue
        order = [seeds[i - 1] for i in SEED_ORDER_32]
        champ = Counter()
        for _ in range(n):
            b = order[:]
            while len(b) > 1:
                b = [_elo_winner(b[i], b[i + 1], elo, mu, s) for i in range(0, len(b), 2)]
            champ[b[0]] += 1
        actual = CHAMPIONS[year]
        p_act = champ[actual] / n
        rank = [t for t, _ in champ.most_common()].index(actual) + 1 if actual in champ else 99
        top, tc = champ.most_common(1)[0]
        ign.append(-math.log2(max(p_act, 1e-9)))
        print(f"  {year:>5} | {actual:>11} | {p_act:>15.1%} | {rank:>4}. | {top} {tc/n:.0%}")
    print(f"\n  Mittlere Ignoranz: {sum(ign)/len(ign):.2f} bit  "
          f"(uniform waeren {math.log2(32):.2f} bit -> niedriger = besser)")
    print("  Hinweis: Naeherung (generischer Baum, keine Gruppenphase), nur 3 Turniere.")


if __name__ == "__main__":
    reliability()
    print("\n" + "=" * 64 + "\n")
    historical_backtest()
    print("\n" + "=" * 64 + "\n")
    champion_backtest()
