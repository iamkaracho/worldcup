#!/usr/bin/env python3
"""
Hypothesentest: Gibt es einen HOEHEN-Heimvorteil ueber den normalen Heimvorteil
hinaus? (Anlass: Mexiko spielt 2026 zwei Gruppenspiele auf 2240 m im Azteca.)

Modell:  log lam_heim = mu + s*(elo_diff)/400 + h*heim + alt*hoehenheim
         (hoehenheim = Heimspiel in Stadt >= ~1800 m)
Fit auf Spielen 2010-2024, Out-of-sample-Check auf 2025+ — gesamt UND auf dem
Teilsample der Hoehen-Heimspiele (nur dort unterscheiden sich die Modelle).
Diszipliniert: nur uebernehmen, wenn der Log-Loss dort sinkt. Nur Stdlib.
"""

import csv
import math

import calibrate
import validate as V

TEST_FROM = "2025-01-01"
TRAIN_FROM = "2010-01-01"

# Staedte >= ~1800 m, in denen results.csv nennenswert Laenderspiele hat
HIGH = {"La Paz", "El Alto", "Quito", "Bogotá", "Bogota", "Sucre", "Cochabamba",
        "Arequipa", "Cusco", "Mexico City", "Ciudad de México", "Toluca",
        "Addis Ababa", "Addis Abeba", "Asmara", "Sana'a", "Sanaa", "Thimphu",
        "Nairobi", "Quetzaltenango"}


def build(rows, elo):
    out = []
    for r in rows:
        h, a = r["home_team"], r["away_team"]
        if h in elo and a in elo and r["home_score"] not in ("", "NA") \
                and r["date"] >= TRAIN_FROM:
            hf = 0 if r["neutral"].upper() == "TRUE" else 1
            out.append({"date": r["date"], "elo_diff": elo[h] - elo[a],
                        "hg": int(r["home_score"]), "ag": int(r["away_score"]),
                        "hf": hf, "af": hf * (1 if r["city"] in HIGH else 0)})
    return out


def fit(train, with_alt, lr=0.3, iters=6000, l2=0.001):
    mu, s, h, alt = math.log(1.35), 0.0, 0.0, 0.0
    n = len(train)
    for _ in range(iters):
        gmu = gs = gh = galt = 0.0
        for m in train:
            d = m["elo_diff"] / V.ELO_DENOM
            eh = max(-2.0, min(3.0, mu + s * d + h * m["hf"] + alt * m["af"]))
            ea = max(-2.0, min(3.0, mu - s * d))
            rh = m["hg"] - math.exp(eh)
            ra = m["ag"] - math.exp(ea)
            gmu += rh + ra
            gs += (rh - ra) * d
            gh += rh * m["hf"]
            galt += rh * m["af"]
        mu += lr * gmu / n
        s += lr * (gs / n - l2 * s)
        h += lr * (gh / n - l2 * h)
        if with_alt:
            alt += lr * (galt / n - l2 * alt)
    return mu, s, h, alt


def wdl_logloss(test, mu, s, h, alt):
    tot = 0.0
    for m in test:
        d = m["elo_diff"] / V.ELO_DENOM
        lh = math.exp(mu + s * d + h * m["hf"] + alt * m["af"])
        la = math.exp(mu - s * d)
        ph = pd = pa = 0.0
        for i in range(11):
            pi = math.exp(-lh) * lh ** i / math.factorial(i)
            for j in range(11):
                p = pi * math.exp(-la) * la ** j / math.factorial(j)
                if i > j:    ph += p
                elif i == j: pd += p
                else:        pa += p
        z = ph + pd + pa
        res = (m["hg"] > m["ag"]) and ph / z or (m["hg"] == m["ag"]) and pd / z or pa / z
        tot -= math.log(max(res, 1e-12))
    return tot / len(test)


def main():
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    elo = V.compute_elo_until(rows, TEST_FROM)
    M = build(rows, elo)
    train = [m for m in M if m["date"] < TEST_FROM]
    test = [m for m in M if m["date"] >= TEST_FROM]
    test_alt = [m for m in test if m["af"]]
    train_alt = [m for m in train if m["af"]]

    # deskriptiv: Heim-Tordifferenz auf Hoehe vs. normal (Trainingsdaten)
    def avg_gd(ms):
        return sum(m["hg"] - m["ag"] for m in ms) / max(len(ms), 1)
    norm_home = [m for m in train if m["hf"] and not m["af"]]
    print(f"Deskriptiv (Train 2010-24): Heim-Tordifferenz normal {avg_gd(norm_home):+.2f}"
          f" ({len(norm_home)} Sp.)  |  auf Hoehe {avg_gd(train_alt):+.2f}"
          f" ({len(train_alt)} Sp.)\n")

    mu0, s0, h0, _ = fit(train, with_alt=False)
    mu1, s1, h1, alt = fit(train, with_alt=True)
    print(f"Basis:  mu={mu0:.3f} s={s0:.3f} heim={h0:.3f}")
    print(f"+Alt:   mu={mu1:.3f} s={s1:.3f} heim={h1:.3f} HOEHE={alt:+.3f} log-Tore"
          f"  (x{math.exp(alt):.2f} Heim-Tore)\n")

    print(f"Out-of-sample 2025+  (gesamt {len(test)} Spiele, davon {len(test_alt)} Hoehen-Heimspiele):")
    print(f"  {'':<24}{'gesamt':>9}{'nur Hoehe':>11}")
    print(f"  {'Basis (nur Heim)':<24}{wdl_logloss(test, mu0, s0, h0, 0):>9.4f}"
          f"{wdl_logloss(test_alt, mu0, s0, h0, 0):>11.4f}")
    print(f"  {'+ Hoehen-Term':<24}{wdl_logloss(test, mu1, s1, h1, alt):>9.4f}"
          f"{wdl_logloss(test_alt, mu1, s1, h1, alt):>11.4f}")


if __name__ == "__main__":
    main()
