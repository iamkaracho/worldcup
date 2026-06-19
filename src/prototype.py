#!/usr/bin/env python3
"""
Prototyp: WM-Sieger-Prognose nach Klement (Rekonstruktionsanalyse).

Minimaler Durchstich der kompletten Mechanik aus MODELLPLANUNG.md:

    Rohdaten -> log/z-Standardisierung -> Staerke-Score
             -> logistische Paar-Wahrscheinlichkeit (mit Zufallsfaktor)
             -> Monte-Carlo ueber einen K.-o.-Baum
             -> P(Titel) je Team + modaler Turnierbaum

Bewusst nur Standardbibliothek (kein numpy noetig). Daten in ../data/teams.csv
sind ILLUSTRATIV. Variable 3 (Fussball-Verankerung) = Kader-Marktwert-Proxy.
"""

import csv
import math
import os
import random
from collections import Counter, defaultdict

# --- Konfiguration -----------------------------------------------------------

# Gewichte der Staerke-Variablen (summieren sich nicht zwingend zu 1).
# FIFA-Punkte bekommen das hoechste Gewicht (aktuelle Form), die strukturellen
# Variablen erklaeren "Potenzial". Spaeter per Backtest zu kalibrieren.
WEIGHTS = {
    "bip_pc":       0.8,   # Wohlstand / Infrastruktur
    "bevoelkerung": 0.6,   # Bevoelkerungsgroesse
    "marktwert":    1.0,   # Verankerung des Fussballs (Proxy)
    "fifa_punkte":  1.6,   # Position Weltrangliste  <- staerkster Praediktor
}

# Variablen mit abnehmendem Grenznutzen werden vor der Standardisierung logarithmiert.
LOG_VARS = {"bip_pc", "bevoelkerung", "marktwert"}

# Temperatur tau = Klements "Zufallsfaktor".
#   klein  -> staerkeres Team gewinnt fast immer (unrealistisch)
#   gross  -> mehr Zufall / Ueberraschungen
TAU = 1.0

N_SIMS = 50_000
SEED = 42  # Reproduzierbarkeit; im echten Lauf entfernen oder variieren.

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "teams.csv")


# --- 1. Daten einlesen -------------------------------------------------------

def load_teams(path):
    teams = {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    header = rows[0]
    for row in rows[1:]:
        rec = dict(zip(header, row))
        teams[rec["team"]] = {k: float(v) for k, v in rec.items() if k != "team"}
    return teams


# --- 2. Feature-Aufbereitung: log + z-Standardisierung -----------------------

def standardize(teams):
    feats = {t: dict(v) for t, v in teams.items()}
    for var in WEIGHTS:
        vals = []
        for t in feats:
            x = feats[t][var]
            if var in LOG_VARS:
                x = math.log(x)
            feats[t][var] = x
            vals.append(x)
        mean = sum(vals) / len(vals)
        sd = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5 or 1.0
        for t in feats:
            feats[t][var] = (feats[t][var] - mean) / sd
    return feats


# --- 3. Staerke-Score --------------------------------------------------------

def strength_scores(feats):
    return {
        t: sum(WEIGHTS[var] * feats[t][var] for var in WEIGHTS)
        for t in feats
    }


# --- 4. Paar-Wahrscheinlichkeit (logistisch, mit Zufallsfaktor tau) ----------

def p_win(si, sj, tau):
    return 1.0 / (1.0 + math.exp(-(si - sj) / tau))


def play(a, b, scores, tau):
    """Ein K.-o.-Spiel: gibt den Sieger zurueck (Verlaengerung/Elfmeter via Zufall)."""
    return a if random.random() < p_win(scores[a], scores[b], tau) else b


# --- 5. Turnierbaum (Prototyp: 8 Teams, Viertelfinale -> Finale) -------------

# Bracket so gesetzt, dass DE und FR in der Top-Haelfte frueh aufeinandertreffen
# koennten (illustriert Klements "DE trifft frueh auf Frankreich").
BRACKET = [
    ("Niederlande", "Portugal"),
    ("Deutschland", "Frankreich"),
    ("Argentinien", "Spanien"),
    ("Brasilien",   "England"),
]


def simulate_once(scores, tau):
    """Spielt den Baum einmal aus. Gibt (Sieger, {team: erreichte_runde}) zurueck."""
    reached = {t: "Viertelfinale" for pair in BRACKET for t in pair}
    round_names = ["Halbfinale", "Finale", "Sieger"]
    teams = [play(a, b, scores, tau) for a, b in BRACKET]
    for rname in round_names:
        for t in teams:
            reached[t] = rname
        if len(teams) == 1:
            break
        teams = [play(teams[i], teams[i + 1], scores, tau)
                 for i in range(0, len(teams), 2)]
    return teams[0], reached


# --- 6. Monte-Carlo + Aggregation -------------------------------------------

def run(scores, n=N_SIMS, tau=TAU):
    titles = Counter()
    bracket_paths = Counter()       # fuer "modalen" Turnierbaum
    exit_round = defaultdict(Counter)
    for _ in range(n):
        winner, reached = simulate_once(scores, tau)
        titles[winner] += 1
        # Verlauf der oberen Haelfte als signierter Pfad merken
        bracket_paths[tuple(sorted(reached.items()))] += 1
        for t, r in reached.items():
            exit_round[t][r] += 1
    return titles, exit_round, bracket_paths


# --- Ausgabe -----------------------------------------------------------------

def main():
    if SEED is not None:
        random.seed(SEED)

    teams = load_teams(DATA_PATH)
    feats = standardize(teams)
    scores = strength_scores(feats)

    print("=== Staerke-Score (hoeher = staerker) ===")
    for t, s in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<13} {s:+.3f}")

    titles, exit_round, paths = run(scores)
    n = sum(titles.values())

    print(f"\n=== P(Weltmeister)  ({n:,} Simulationen, tau={TAU}) ===")
    for t, c in titles.most_common():
        bar = "#" * round(50 * c / n)
        print(f"  {t:<13} {c/n:6.1%}  {bar}")

    print("\n=== Erwartetes Ausscheiden (Anteil je erreichter Runde) ===")
    for t, _ in titles.most_common():
        dist = exit_round[t]
        parts = "  ".join(f"{r}:{dist[r]/n:.0%}"
                          for r in ("Sieger", "Finale", "Halbfinale", "Viertelfinale")
                          if dist[r])
        print(f"  {t:<13} {parts}")

    champ = titles.most_common(1)[0][0]
    print(f"\n>>> Modell-Tipp Weltmeister: {champ}")
    print("    (Artikel: Klement tippt die Niederlande.)")


if __name__ == "__main__":
    main()
