#!/usr/bin/env python3
"""
Hypothesentest: Bringt HEAD-TO-HEAD (frühere direkte Duelle der beiden Teams) einen
Out-of-sample-Mehrwert ÜBER die Teamstärke (Elo/Marktwert/FIFA) hinaus?

Frage hinter der Frage: Gibt es echte „Angstgegner"-Effekte, oder steckt alles schon
in der Stärke? Das RF-Modell im Screenshot listet h2h hoch nach „importance" — aber
Feature-Importance ist KEIN Out-of-sample-Beweis (kann Overfitting spiegeln).

Mechanik: Basis = att/def+decay (auf Train gefittet). Dann h2h-Feature je Spiel aus den
VORHERIGEN Duellen (orientierte Tordifferenz, zeit-gewichtet) und ein Koeffizient gamma,
der die Lambdas anpasst: lh*=exp(+g*f/2), la*=exp(-g*f/2). gamma per 1-D-MLE auf Train,
dann Ergebnis-Log-Loss auf Test (ab TEST_FROM) vs. Basis. Nur Standardbibliothek.
"""

import csv
import math
from datetime import date

import calibrate as C
import model

HALFLIFE = C.HALFLIFE_DAYS
H2H_HL_DAYS = 365 * 8        # Duelle verlieren über ~8 Jahre an Gewicht
CAP = 3.0                    # orientierte Tordiff je Duell kappen


def _d(s):
    return date(*map(int, s.split("-")))


def load():
    """Strukturierte Matches (wie calibrate) + EN-Teamnamen + h2h-Feature (nur Vorduelle)."""
    teams = model.load_teams(model.TEAMS_PATH)
    feats = model.standardized_features(teams)
    raw = []
    with open(C.RESULTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("", "NA"):
                continue
            raw.append(r)
    raw.sort(key=lambda r: r["date"])

    # h2h-Historie: pro ungeordnetem Teampaar Liste (datum, orientierte_gd zu home-key)
    hist = {}
    out = []
    for r in raw:
        ht, at = r["home_team"], r["away_team"]
        hg, ag = int(r["home_score"]), int(r["away_score"])
        key = tuple(sorted((ht, at)))
        prior = hist.get(key, [])
        # h2h-Feature aus dem Blick des AKTUELLEN Heimteams, zeitgewichtet
        num = den = 0.0
        for pd_, first, gd in prior:
            wk = 0.5 ** ((_d(r["date"]) - pd_).days / H2H_HL_DAYS)
            g = gd if first == ht else -gd     # auf aktuelles Heimteam orientieren
            num += wk * max(-CAP, min(CAP, g)); den += wk
        h2h = num / den if den else 0.0
        n = len(prior)

        h, a = C.EN2DE.get(ht), C.EN2DE.get(at)
        if r["date"] >= C.CUTOFF and h and a:
            out.append({"date": r["date"], "xh": feats[h], "xa": feats[a],
                        "delta": {v: feats[h][v] - feats[a][v] for v in C.VARS},
                        "hg": hg, "ag": ag,
                        "hf": 0 if r["neutral"].upper() == "TRUE" else 1,
                        "h2h": h2h, "h2h_n": n})
        # Historie fortschreiben (orientierte gd zum sortiert-ersten Key-Team)
        gd_first = hg - ag if ht == key[0] else ag - hg
        hist.setdefault(key, []).append((_d(r["date"]), key[0], gd_first))
    return out


def _ll(test, p, gamma):
    tot = 0.0
    for m in test:
        lh, la = C.lambdas(p, m)
        adj = math.exp(gamma * m["h2h"] / 2.0)
        lh, la = lh * adj, la / adj
        ph = pd = pa = 0.0
        for i in range(11):
            pi = math.exp(-lh) * lh ** i / math.factorial(i)
            for j in range(11):
                pij = pi * math.exp(-la) * la ** j / math.factorial(j) * C.dc_tau(i, j, lh, la, p.get("rho", 0))
                if i > j: ph += pij
                elif i == j: pd += pij
                else: pa += pij
        z = ph + pd + pa
        act = (ph if m["hg"] > m["ag"] else pd if m["hg"] == m["ag"] else pa) / z
        tot -= math.log(max(act, 1e-9))
    return tot / len(test)


def main():
    matches = load()
    train = [m for m in matches if m["date"] < C.TEST_FROM]
    test = [m for m in matches if m["date"] >= C.TEST_FROM]
    withp = sum(1 for m in test if m["h2h_n"] > 0)
    print(f"Train {len(train)}, Test {len(test)} (davon {withp} mit ≥1 Vorduell, "
          f"mittl. Vorduelle {sum(m['h2h_n'] for m in test)/len(test):.1f})\n")

    p = C.fit_split(train, iters=5000, halflife=HALFLIFE)
    p["rho"] = C.fit_rho(train, p)

    base = _ll(test, p, 0.0)
    # gamma per Grid-Suche auf TRAIN
    best = (0.0, 1e9)
    for k in range(-40, 41):
        g = k / 100.0
        l = _ll(train, p, g)
        if l < best[1]:
            best = (g, l)
    g_fit = best[0]
    print(f"gamma (auf Train optimiert): {g_fit:+.2f}   (0 = h2h ohne Wirkung)\n")
    print(f"  {'Variante':<30}{'Test-LogLoss':>13}{'Δ':>9}")
    print(f"  {'Basis (att/def+decef)':<30}{base:>13.4f}{0.0:>+9.4f}")
    for g, lbl in [(g_fit, f"+ h2h (gamma={g_fit:+.2f})"), (0.20, "+ h2h (gamma=+0.20 fest)")]:
        ll = _ll(test, p, g)
        tag = "  <- besser" if ll < base - 1e-4 else ""
        print(f"  {lbl:<30}{ll:>13.4f}{ll-base:>+9.4f}{tag}")


if __name__ == "__main__":
    main()
