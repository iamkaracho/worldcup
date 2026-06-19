#!/usr/bin/env python3
"""
Hypothesentest: Gibt es einen "Turniermannschaft"-Effekt — Teams, die bei WMs
systematisch ueber/unter ihrer Staerke spielen?

Modell: ein team-spezifischer Turnier-Bonus beta_i (in Elo-Punkten), der WAEHREND
eines Turniers auf die Staerke des Teams addiert wird. beta_i wird per 1-D-MLE aus
den Turnierspielen geschaetzt und zur Mitte GESCHRUMPFT (n/(n+K)), weil pro Team nur
wenige Turnierspiele vorliegen.

Sauberer Test: Leave-one-tournament-out. beta aus den ANDEREN Turnieren schaetzen,
auf die ausgelassene WM anwenden, Ergebnis-Log-Loss mit/ohne vergleichen. Antwortet
ehrlich, ob "Turniermannschaft" Signal ist oder Narrativ. Nur Standardbibliothek.
"""

import csv
import json
import math
import os

import validate as V

YEARS = list(V.WORLD_CUPS)          # 2014, 2018, 2022
BETA_GRID = [b for b in range(-160, 161, 4)]
SHRINK_K = 8                        # n/(n+K): Team mit 8 Spielen -> 50% Gewicht
DENOM = V.ELO_DENOM


def build_tournaments(rows):
    """Pro WM: pre-Turnier-Elo, gefittetes Tormodell (mu,s,h), Liste der Spiele."""
    tour = {}
    for y, (tr, t0, t1) in V.WORLD_CUPS.items():
        elo = V.compute_elo_until(rows, t0)
        mu, s, h = V.fit_elo_poisson(V._build(
            [r for r in rows if tr <= r["date"] < t0], elo))
        games = []
        for r in rows:
            if (t0 <= r["date"] <= t1 and r["tournament"] == "FIFA World Cup"
                    and r["home_score"] not in ("", "NA")
                    and r["home_team"] in elo and r["away_team"] in elo):
                games.append((r["home_team"], r["away_team"],
                              int(r["home_score"]), int(r["away_score"]),
                              0 if r["neutral"].upper() == "TRUE" else 1))
        tour[y] = {"elo": elo, "p": (mu, s, h), "games": games}
    return tour


def _ll_match(mu, s, h, ei, ej, hf_i, hf_j, gi, gj, beta_i=0.0, beta_j=0.0):
    """Poisson-Loglik eines Spiels aus Sicht (Tore i, Tore j); beta verschiebt Elo."""
    li = math.exp(mu + s * ((ei + beta_i) - (ej + beta_j)) / DENOM + h * hf_i)
    lj = math.exp(mu + s * ((ej + beta_j) - (ei + beta_i)) / DENOM + h * hf_j)
    return gi * math.log(li) - li + gj * math.log(lj) - lj


def estimate_beta(entries):
    """entries: Liste (mu,s,h, elo_i, elo_j, hf_i, hf_j, gi, gj). MLE ueber beta_i, dann Shrink."""
    if not entries:
        return 0.0
    best_b, best_ll = 0.0, -1e18
    for b in BETA_GRID:
        ll = sum(_ll_match(mu, s, h, ei, ej, hi, hj, gi, gj, beta_i=b)
                 for (mu, s, h, ei, ej, hi, hj, gi, gj) in entries)
        if ll > best_ll:
            best_ll, best_b = ll, b
    n = len(entries)
    return best_b * n / (n + SHRINK_K)


def team_entries(tour, years, team):
    """Alle Turnierspiele von `team` ueber die angegebenen Jahre (i-Perspektive)."""
    out = []
    for y in years:
        mu, s, h = tour[y]["p"]
        elo = tour[y]["elo"]
        for ht, at, hg, ag, hf in tour[y]["games"]:
            if team == ht:
                out.append((mu, s, h, elo[ht], elo[at], hf, 0, hg, ag))
            elif team == at:
                out.append((mu, s, h, elo[at], elo[ht], 0, hf, ag, hg))
    return out


def _wdl_logloss(tour, year, beta):
    """Ergebnis-Log-Loss der WM `year` mit Team-Bonus beta (dict team->beta)."""
    mu, s, h = tour[year]["p"]
    elo = tour[year]["elo"]
    tot = 0.0
    for ht, at, hg, ag, hf in tour[year]["games"]:
        bi, bj = beta.get(ht, 0.0), beta.get(at, 0.0)
        li = math.exp(mu + s * ((elo[ht] + bi) - (elo[at] + bj)) / DENOM + h * hf)
        lj = math.exp(mu + s * ((elo[at] + bj) - (elo[ht] + bi)) / DENOM)
        ph = pd = pa = 0.0
        for i in range(11):
            pi = math.exp(-li) * li ** i / math.factorial(i)
            for j in range(11):
                pj = math.exp(-lj) * lj ** j / math.factorial(j)
                if i > j:    ph += pi * pj
                elif i == j: pd += pi * pj
                else:        pa += pi * pj
        z = ph + pd + pa or 1.0
        ph, pd, pa = ph / z, pd / z, pa / z
        act = ph if hg > ag else pd if hg == ag else pa
        tot += -math.log(max(act, 1e-9))
    return tot / len(tour[year]["games"])


def main():
    rows = list(csv.DictReader(open(V.calibrate.RESULTS_PATH, encoding="utf-8")))
    tour = build_tournaments(rows)
    all_teams = sorted({t for y in YEARS for g in tour[y]["games"] for t in (g[0], g[1])})

    # --- Deskriptiv: beta aus ALLEN 3 Turnieren (nur zur Anschauung) ---
    beta_all = {t: estimate_beta(team_entries(tour, YEARS, t)) for t in all_teams}
    ranked = sorted(beta_all.items(), key=lambda kv: -kv[1])
    print("Geschaetzter Turnier-Bonus beta (Elo-Punkte, geschrumpft, aus 2014/18/22):")
    print("  groesste Ueberperformer:")
    for t, b in ranked[:6]:
        print(f"    {t:<16} {b:+5.1f}")
    print("  groesste Unterperformer:")
    for t, b in ranked[-6:]:
        print(f"    {t:<16} {b:+5.1f}")

    # --- Sauberer Test: Leave-one-tournament-out ---
    print("\nLeave-one-tournament-out — Ergebnis-Log-Loss (niedriger = besser):")
    print(f"  {'WM':>5} | {'nur Elo':>9} | {'Elo + Turnier-Bonus':>20}")
    base_tot = bonus_tot = n_tot = 0.0
    loo = []
    for test in YEARS:
        others = [y for y in YEARS if y != test]
        beta = {t: estimate_beta(team_entries(tour, others, t)) for t in all_teams}
        ll_base = _wdl_logloss(tour, test, {})
        ll_bonus = _wdl_logloss(tour, test, beta)
        ng = len(tour[test]["games"])
        base_tot += ll_base * ng; bonus_tot += ll_bonus * ng; n_tot += ng
        loo.append({"year": test, "base": round(ll_base, 4), "bonus": round(ll_bonus, 4)})
        mark = "besser" if ll_bonus < ll_base else "schlechter"
        print(f"  {test:>5} | {ll_base:>9.4f} | {ll_bonus:>17.4f}  ({mark})")
    print(f"  {'GESAMT':>5} | {base_tot/n_tot:>9.4f} | {bonus_tot/n_tot:>17.4f}")

    better = bonus_tot < base_tot
    result = {
        "overperformers": [[t, round(b, 1)] for t, b in ranked[:6]],
        "underperformers": [[t, round(b, 1)] for t, b in ranked[-6:][::-1]],
        "loo": loo,
        "overall_base": round(base_tot / n_tot, 4),
        "overall_bonus": round(bonus_tot / n_tot, 4),
        "better": better,
    }
    with open(os.path.join(V.model._HERE, "..", "output", "tournament_myth.json"),
              "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n=> Turnier-Bonus {'HILFT out-of-sample' if better else 'hilft NICHT'} "
          f"({(base_tot-bonus_tot)/base_tot*100:+.2f}%).")
    if not better:
        print("   'Turniermannschaft' ist out-of-sample nicht nachweisbar — die beta sind")
        print("   im Wesentlichen Rauschen aus Mini-Stichproben. Genau Klements These.")


if __name__ == "__main__":
    main()
