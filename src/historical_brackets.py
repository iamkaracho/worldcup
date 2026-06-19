#!/usr/bin/env python3
"""
Historischer Sweep mit ECHTEN Brackets (rekonstruiert aus results.csv).

Pro WM:
  - Gruppen aus den Round-Robin-Spielen rekonstruiert (Zusammenhangskomponenten).
  - Tatsaechliche Endstaende je Gruppe -> jede(r) Team-Position (group_idx, Platz).
  - R16-Paarungen + Baum (R16->QF->SF->Finale) aus den echten K.-o.-Spielen abgeleitet
    (Verknuepfung ueber 'Sieger taucht in naechster Runde auf').
  - Dann GRUPPENPHASE neu simuliert (Elo-Modell), Qualifikanten in dieselben Slots,
    Baum ausgespielt -> Titelwahrscheinlichkeiten.

Elo-Modell (ergebnisbasiert), da historisch keine Marktwerte/FIFA-Punkte. Nur Stdlib.
"""

import csv
import math
import random
from collections import defaultdict, Counter

import model
import validate as V

# (Jahr, Trainingsstart, Turnierstart, -ende, Weltmeister, Anzahl Gruppen)
WCS = [
    ("1990", "1988-06-01", "1990-06-08", "1990-07-09", "Germany", 6),
    ("1994", "1992-06-01", "1994-06-17", "1994-07-18", "Brazil", 6),
    ("1998", "1996-06-01", "1998-06-10", "1998-07-13", "France", 8),
    ("2002", "2000-05-01", "2002-05-31", "2002-07-01", "Brazil", 8),
    ("2006", "2004-06-01", "2006-06-09", "2006-07-10", "Italy", 8),
    ("2010", "2008-06-01", "2010-06-11", "2010-07-12", "Spain", 8),
    ("2014", "2012-06-01", "2014-06-12", "2014-07-14", "Germany", 8),
    ("2018", "2016-06-01", "2018-06-14", "2018-07-16", "France", 8),
    ("2022", "2020-06-01", "2022-11-20", "2022-12-19", "Argentina", 8),
]


def _teams(m):
    return {m["home_team"], m["away_team"]}


def group_standings(gteams, gm, elo):
    st = {t: [0, 0, 0] for t in gteams}            # pts, gf, ga
    for r in gm:
        h, a = r["home_team"], r["away_team"]
        if h in st and a in st:
            hg, ag = int(r["home_score"]), int(r["away_score"])
            st[h][1] += hg; st[h][2] += ag; st[a][1] += ag; st[a][2] += hg
            if hg > ag:   st[h][0] += 3
            elif ag > hg: st[a][0] += 3
            else:         st[h][0] += 1; st[a][0] += 1
    return sorted(gteams, key=lambda t: (st[t][0], st[t][1] - st[t][2], st[t][1],
                                         elo.get(t, 0)), reverse=True)


def reconstruct(wc, n_groups, champ, elo):
    """Liefert (groups, r16_slotpairs, tree) oder None bei Fehlschlag.
    slot = (group_idx, pos 1..4). tree: dict matchkey -> (childA, childB)."""
    gmc = n_groups * 6
    gm, ko = wc[:gmc], wc[gmc:]
    if len(ko) < 16:
        return None
    # Gruppen = Zusammenhangskomponenten des Gruppenspiel-Graphen
    adj = defaultdict(set)
    for r in gm:
        adj[r["home_team"]].add(r["away_team"])
        adj[r["away_team"]].add(r["home_team"])
    seen, groups = set(), []
    for t in adj:
        if t in seen:
            continue
        comp, stack = {t}, [t]
        while stack:
            for y in adj[stack.pop()]:
                if y not in comp:
                    comp.add(y); stack.append(y)
        groups.append(sorted(comp)); seen |= comp
    if len(groups) != n_groups or any(len(g) != 4 for g in groups):
        return None

    # Team -> (group_idx, Platz). Positionen nur ueber die TATSAECHLICH Qualifizierten
    # (Teams, die in der K.-o.-Phase auftauchen) -> robust gegen Fair-Play-Tiebreaks.
    ko_teams = set().union(*[_teams(m) for m in ko])
    slot_of = {}
    for gi, g in enumerate(groups):
        quals = [t for t in group_standings(g, gm, elo) if t in ko_teams]
        for pos, t in enumerate(quals):
            slot_of[t] = (gi, pos + 1)

    R16, QF, SF, last2 = ko[:8], ko[8:12], ko[12:14], ko[14:16]
    final = next((m for m in last2 if champ in _teams(m)), None)
    if final is None or len(R16) != 8:
        return None

    def child_idx(match, prev):
        kids = []
        for t in _teams(match):
            for i, pm in enumerate(prev):
                if t in _teams(pm):
                    kids.append(i); break
        return kids if len(kids) == 2 else None

    tree = {}
    for j, m in enumerate(QF):
        c = child_idx(m, R16)
        if not c: return None
        tree[("QF", j)] = [("R16", c[0]), ("R16", c[1])]
    for j, m in enumerate(SF):
        c = child_idx(m, QF)
        if not c: return None
        tree[("SF", j)] = [("QF", c[0]), ("QF", c[1])]
    c = child_idx(final, SF)
    if not c: return None
    tree[("F", 0)] = [("SF", c[0]), ("SF", c[1])]

    r16_slots = [(slot_of[m["home_team"]], slot_of[m["away_team"]]) for m in R16]
    return groups, r16_slots, tree


def simulate(groups, r16_slots, tree, n_groups, elo, mu, s):
    # Gruppenphase neu simulieren -> sim-Endstand je Gruppe
    sim_rank = []
    for g in groups:
        st = {t: [0, 0, 0] for t in g}
        for i in range(4):
            for j in range(i + 1, 4):
                a, b = g[i], g[j]
                d = (elo[a] - elo[b]) / V.ELO_DENOM
                ga = model._poisson(math.exp(mu + s * d))
                gb = model._poisson(math.exp(mu - s * d))
                st[a][1] += ga; st[a][2] += gb; st[b][1] += gb; st[b][2] += ga
                if ga > gb:   st[a][0] += 3
                elif gb > ga: st[b][0] += 3
                else:         st[a][0] += 1; st[b][0] += 1
        sim_rank.append(sorted(g, key=lambda t: (st[t][0], st[t][1] - st[t][2],
                                                  st[t][1], random.random()), reverse=True))
    # beste Dritte (nur 6-Gruppen-Format) -> Elo-Zuordnung auf die 3.-Slots
    third_slot_groups = [sp[k][0] for sp in r16_slots for k in (0, 1) if sp[k][1] == 3]
    third_fill = {}
    if third_slot_groups:
        thirds = sorted((gi for gi in range(n_groups)), key=lambda gi: -elo[sim_rank[gi][2]])
        best = thirds[:len(third_slot_groups)]
        for slotgi, simgi in zip(third_slot_groups, best):
            third_fill[slotgi] = sim_rank[simgi][2]

    def team_in_slot(slot):
        gi, pos = slot
        if pos == 3:
            return third_fill.get(gi, sim_rank[gi][2])
        return sim_rank[gi][pos - 1]

    cache = {}

    def resolve(key):
        if key in cache:
            return cache[key]
        if key[0] == "R16":
            sp = r16_slots[key[1]]
            a, b = team_in_slot(sp[0]), team_in_slot(sp[1])
        else:
            (ca, cb) = tree[key]
            a, b = resolve(ca), resolve(cb)
        w = V._elo_winner(a, b, elo, mu, s)
        cache[key] = w
        return w

    return resolve(("F", 0))


def main():
    rows = list(csv.DictReader(open(V.calibrate.RESULTS_PATH, encoding="utf-8")))
    random.seed(model.SEED)
    print("Historischer Sweep mit ECHTEN (rekonstruierten) Brackets — Elo-Modell\n")
    print(f"  {'WM':>5} {'Weltmeister':<13}{'Favorit':<13}{'P(Sieger)':>10}{'Rang':>6}{'Gruppen':>9}")
    hits = 0
    for year, tr, t0, t1, champ, ng in WCS:
        elo = V.compute_elo_until(rows, t0)
        mu, s, _ = V.fit_elo_poisson(V._build(
            [r for r in rows if tr <= r["date"] < t0], elo))
        wc = sorted([r for r in rows if t0 <= r["date"] <= t1
                     and r["tournament"] == "FIFA World Cup"
                     and r["home_score"] not in ("", "NA")], key=lambda r: r["date"])
        rec = reconstruct(wc, ng, champ, elo)
        if rec is None:
            print(f"  {year:>5} {champ:<13}(Bracket-Rekonstruktion fehlgeschlagen)")
            continue
        groups, r16_slots, tree = rec
        champc = Counter()
        for _ in range(2500):
            champc[simulate(groups, r16_slots, tree, ng, elo, mu, s)] += 1
        n = sum(champc.values())
        fav = champc.most_common(1)[0][0]
        order = [t for t, _ in champc.most_common()]
        rank = order.index(champ) + 1 if champ in order else 99
        hits += (fav == champ)
        print(f"  {year:>5} {champ:<13}{fav:<13}{champc.get(champ,0)/n:>9.1%}{rank:>6}"
              f"{len(groups):>6}x4")
    print(f"\n  Modell-Favorit = echter Sieger: {hits}/9  (echte Gruppen + echter K.-o.-Baum)")


if __name__ == "__main__":
    main()
