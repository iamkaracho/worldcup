#!/usr/bin/env python3
"""
Staged Snapshots der WM-2026-Prognose — laufend waehrend des Turniers.

Pro Lauf:
  1. results.csv frisch laden (best effort; offline -> vorhandene Datei).
  2. Gespielte WM-Spiele extrahieren: Gruppenspiele werden FIXIERT (Conditioning),
     entschiedene K.-o.-Spiele ebenso (bei Remis: Sieger aus shootouts.csv, sonst simuliert).
  3. Elo NEU berechnen (inkl. der gespielten WM-Spiele) -> Form fliesst ein.
  4. Rest des Turniers simulieren -> P(Titel) etc. je Team.
  5. Snapshot speichern (output/snapshots/), Historie anhaengen (history.csv),
     Diff zum letzten Snapshot drucken -> man sieht sofort, was "ausbricht".

Idempotent: ohne neue gespielte Spiele wird KEIN neuer Snapshot geschrieben
(ausser --force). So entsteht automatisch genau ein Snapshot pro Spieltag.

Aufruf:  python3 snapshot.py [--force] [--no-download] [--sims N]
Nur Standardbibliothek.
"""

import csv
import json
import math
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime

import calibrate
import automation_status
import model
import validate as V

SNAP_DIR = os.path.join(model._HERE, "..", "output", "snapshots")
OUT_DIR = os.path.join(model._HERE, "..", "output")
RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SHOOTOUTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv"
SHOOTOUTS_PATH = os.path.join(model._HERE, "..", "data", "raw", "shootouts.csv")
WC_START = "2026-06-01"
N_SIMS = 10_000

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        subprocess.run(["curl", "-sL", "--max-time", "60", "-o", dest + ".tmp", url],
                       check=True)
        if os.path.getsize(dest + ".tmp") > 1000:
            os.replace(dest + ".tmp", dest)
            return True
    except Exception:
        pass
    if os.path.exists(dest + ".tmp"):
        os.remove(dest + ".tmp")
    return False


def shootout_winners():
    if not os.path.exists(SHOOTOUTS_PATH):
        return {}
    out = {}
    with open(SHOOTOUTS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["date"] >= WC_START:
                out[frozenset((r["home_team"], r["away_team"]))] = r["winner"]
    return out


def group_fixture_keys():
    path = os.path.join(model._HERE, "..", "output", "group_fixtures.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        fixtures = json.load(f)
    keys = set()
    for x in fixtures:
        keys.add((x["date"], x["home"], x["away"]))
        keys.add((x["date"], x["away"], x["home"]))
    return keys


def played_wc_games(rows, team2group):
    """(fixed_group, ko_winners, n_played, letzte_datum)"""
    pens = shootout_winners()
    group_keys = group_fixture_keys()
    fixed, ko = {}, {}
    n, last = 0, ""
    for r in rows:
        if (r["date"] < WC_START or "World Cup" not in r["tournament"]
                or r["home_score"] in ("", "NA")):
            continue
        h = calibrate.EN2DE.get(r["home_team"])
        a = calibrate.EN2DE.get(r["away_team"])
        if not h or not a:
            continue
        hg, ag = int(r["home_score"]), int(r["away_score"])
        n += 1
        last = max(last, r["date"])
        is_group = ((r["date"], h, a) in group_keys if group_keys is not None
                    else team2group.get(h) == team2group.get(a))
        if is_group:
            fixed[(h, a)] = (hg, ag)
        else:
            if hg != ag:
                ko[frozenset((h, a))] = h if hg > ag else a
            else:
                w_en = pens.get(frozenset((r["home_team"], r["away_team"])))
                w = calibrate.EN2DE.get(w_en or "")
                if w:
                    ko[frozenset((h, a))] = w
                # sonst: Sieger unbekannt -> Spiel bleibt simuliert
    return fixed, ko, n, last


def live_eval(fixed, ko, scores):
    """Live-Validierung des EINGEFRORENEN Vorturnier-Modells auf den bereits
    gespielten Spielen — die WM als erstes wirklich unberuehrtes Test-Set.
    Gruppenspiele: W/D/L-Log-Loss der Vorturnier-Prognosen (group_fixtures.json)
    vs. Basisrate. K.-o.: Log-Loss 'Wer kommt weiter' vs. Muenzwurf (0.5)."""
    out = {}
    fx_path = os.path.join(model._HERE, "..", "output", "group_fixtures.json")
    if fixed and os.path.exists(fx_path):
        with open(fx_path, encoding="utf-8") as f:
            fx = {(x["home"], x["away"]): x for x in json.load(f)}
        ll = base = n = 0
        for (h, a), (hg, ag) in fixed.items():
            x = fx.get((h, a)) or fx.get((a, h))
            if not x:
                continue
            if (h, a) not in fx:                       # Orientierung drehen
                hg, ag = ag, hg
            p = x["ph"] if hg > ag else x["pd"] if hg == ag else x["pa"]
            b = 0.45 if hg > ag else 0.25 if hg == ag else 0.30
            ll -= math.log(max(p, 1e-12)); base -= math.log(b); n += 1
        if n:
            out["gruppe"] = {"n": n, "logloss": round(ll / n, 4),
                             "basis": round(base / n, 4)}
    if ko:
        ll = n = 0
        for pair, w in ko.items():
            a, b = sorted(pair)
            pw, pd, _, _, _ = model.match_probs(a, b)
            pen = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
            padv = pw + pd * pen
            p = padv if w == a else 1 - padv
            ll -= math.log(max(p, 1e-12)); n += 1
        out["ko"] = {"n": n, "logloss": round(ll / n, 4), "basis": round(math.log(2), 4)}
    return out


MANUAL_PATH = os.path.join(model._HERE, "..", "data", "raw", "manual_results.csv")


def merge_manual(rows):
    """Mergt data/raw/manual_results.csv (gleiche Spalten wie results.csv) hinter den
    Download: Spiele, die upstream noch fehlen, lassen sich sofort selbst eintragen.
    Sobald upstream dasselbe Spiel liefert (date+teams), gewinnt der Download."""
    if not os.path.exists(MANUAL_PATH):
        return rows
    have = {(r["date"], r["home_team"], r["away_team"]) for r in rows
            if r["home_score"] not in ("", "NA")}
    extra = []
    for r in csv.DictReader(open(MANUAL_PATH, encoding="utf-8")):
        if (r["date"], r["home_team"], r["away_team"]) not in have:
            r.setdefault("tournament", "FIFA World Cup")
            r.setdefault("neutral", "FALSE")
            extra.append(r)
    if extra:
        print(f"manual_results.csv: {len(extra)} Spiel(e) ergänzt (upstream noch ohne Ergebnis)")
        # Download-Zeilen ohne Score fuer dieselben Spiele ersetzen
        keys = {(r["date"], r["home_team"], r["away_team"]) for r in extra}
        rows = [r for r in rows
                if (r["date"], r["home_team"], r["away_team"]) not in keys]
        rows.extend(extra)
        rows.sort(key=lambda r: r["date"])
    return rows


def fresh_elo(rows):
    """Elo ueber ALLE gespielten Spiele (inkl. WM) je DE-Team."""
    elo = V.compute_elo_until(rows, "2027-01-01")
    out = {}
    for de, aliases in calibrate.ALIASES.items():
        vals = [elo[e] for e in aliases if e in elo]
        if vals:
            out[de] = round(max(vals), 1)
    return out


def _group_tables(groups, fixed, fairplay):
    out = {}
    for letter, members in groups.items():
        st = {t: {"pts": 0, "gf": 0, "ga": 0, "pl": 0, "tb": 0.0} for t in members}
        res = {}
        for (a, b), (ga, gb) in fixed.items():
            if a in st and b in st:
                res[(a, b)] = (ga, gb)
                st[a]["gf"] += ga; st[a]["ga"] += gb; st[a]["pl"] += 1
                st[b]["gf"] += gb; st[b]["ga"] += ga; st[b]["pl"] += 1
                if ga > gb:
                    st[a]["pts"] += 3
                elif gb > ga:
                    st[b]["pts"] += 3
                else:
                    st[a]["pts"] += 1; st[b]["pts"] += 1
        ranked = model.rank_group(members, st, res, fairplay)
        out[letter] = {"ranked": ranked, "stats": st, "complete": all(st[t]["pl"] >= 3 for t in members)}
    return out


def _ko_probability(a, b, scores):
    pw, pd, _, _, _ = model.match_probs(a, b)
    pen = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
    return max(0.0, min(1.0, pw + pd * pen))


def write_live_bracket(groups, fixed, ko, scores, fairplay, stamp, n_played):
    """Schreibt die aktuell bekannte K.-o.-Lage fuer das Dashboard.
    Vor kompletter Gruppenphase bleibt die Datei bewusst leer, damit das Dashboard
    bei Gruppenspielen bleibt. Danach werden bekannte und offene K.-o.-Paarungen
    als eigene Datenquelle gerendert."""
    path = os.path.join(OUT_DIR, "live_bracket.json")
    tables = _group_tables(groups, fixed, fairplay)
    if not tables or not all(t["complete"] for t in tables.values()):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"available": False, "reason": "group_stage_open",
                       "n_played": n_played, "stamp": stamp}, f, ensure_ascii=False, indent=1)
        return

    winners = {L: tables[L]["ranked"][0] for L in tables}
    runners = {L: tables[L]["ranked"][1] for L in tables}
    thirds = {L: tables[L]["ranked"][2] for L in tables}
    q_letters = set(sorted(tables, key=lambda L: model.third_place_key(thirds[L], tables[L]["stats"]),
                           reverse=True)[:8])
    slot_letter = model.assign_thirds(q_letters)

    def spec_label(spec):
        kind, val = spec
        if kind == "W":
            return f"Sieger {val}", winners[val]
        if kind == "R":
            return f"Zweiter {val}", runners[val]
        letter = slot_letter[val]
        return f"Dritter {letter}", thirds[letter]

    cache = {}
    games = []

    def resolve(m):
        if m in cache:
            return cache[m]
        if m in model.R32:
            l1, a = spec_label(model.R32[m][0])
            l2, b = spec_label(model.R32[m][1])
        else:
            ca, cb = model.TREE[m]
            a, b = resolve(ca), resolve(cb)
            l1, l2 = f"Sieger {ca}", f"Sieger {cb}"
        pair = frozenset((a, b))
        winner = ko.get(pair)
        if winner is None and m not in model.R32 and (a is None or b is None):
            games.append({"match": m, "round": model.ROUND_OF[m], "home": None, "away": None,
                          "home_label": l1, "away_label": l2, "played": False})
            cache[m] = None
            return None
        p_home = _ko_probability(a, b, scores) if a and b else None
        games.append({"match": m, "round": model.ROUND_OF[m], "home": a, "away": b,
                      "home_label": l1, "away_label": l2, "played": winner is not None,
                      "winner": winner, "p_home": round(p_home, 4) if p_home is not None else None,
                      "p_away": round(1 - p_home, 4) if p_home is not None else None})
        cache[m] = winner
        return winner

    for m in range(73, 89):
        resolve(m)
    for m in range(89, 105):
        if m in model.TREE:
            ca, cb = model.TREE[m]
            if cache.get(ca) and cache.get(cb):
                resolve(m)

    games.sort(key=lambda x: x["match"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"available": True, "stamp": stamp, "n_played": n_played,
                   "qualified_thirds": sorted(q_letters),
                   "third_slot_letter": {str(k): v for k, v in slot_letter.items()},
                   "games": games}, f, ensure_ascii=False, indent=1)


def main():
    force = "--force" in sys.argv
    no_dl = "--no-download" in sys.argv
    sims = int(sys.argv[sys.argv.index("--sims") + 1]) if "--sims" in sys.argv else N_SIMS
    os.makedirs(SNAP_DIR, exist_ok=True)

    if not no_dl:
        ok = download(RESULTS_URL, calibrate.RESULTS_PATH)
        download(SHOOTOUTS_URL, SHOOTOUTS_PATH)
        print(f"results.csv: {'aktualisiert' if ok else 'Download fehlgeschlagen, nutze lokale Datei'}")

    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    team2group = {t: g for g, ms in groups.items() for t in ms}
    if os.path.exists(calibrate.RESULTS_PATH):
        rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    else:
        rows = []
        print(f"{calibrate.RESULTS_PATH} fehlt; nutze nur manual_results.csv, falls vorhanden.")
    rows = merge_manual(rows)

    fixed, ko, n_played, last_date = played_wc_games(rows, team2group)

    prev_files = sorted(f for f in os.listdir(SNAP_DIR) if f.startswith("snapshot_"))
    prev = None
    if prev_files:
        with open(os.path.join(SNAP_DIR, prev_files[-1]), encoding="utf-8") as f:
            prev = json.load(f)
    if prev and n_played < prev["n_played"]:
        msg = (f"Erkannte Spiele ({n_played}) liegen hinter letztem Snapshot "
               f"({prev['n_played']}); breche ab, um Outputs nicht zurückzusetzen")
        automation_status.write_step("snapshot", False, msg, {
            "n_played": n_played,
            "previous_n_played": prev["n_played"],
            "changed": False,
        })
        print(msg)
        return

    # Live-Validierung mit dem EINGEFRORENEN Vorturnier-Modell (vor Elo-Update!)
    frozen_scores, _ = model.build_scores(teams)
    ev = live_eval(fixed, ko, frozen_scores)

    # Elo frisch (Form!), Ausfaelle wie gehabt; Kalibrierung bleibt fix.
    elo_now = fresh_elo(rows) if rows else {}
    teams = {t: dict(v) for t, v in teams.items()}
    for t in teams:
        if t in elo_now:
            teams[t]["elo"] = elo_now[t]
    scores, modus = model.build_scores(teams)

    fairplay = model.load_cards()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    write_live_bracket(groups, fixed, ko, scores, fairplay, stamp, n_played)

    # Schon ein Snapshot mit diesem Stand? -> nichts zu tun.
    if prev and prev["n_played"] == n_played and not force:
        msg = f"Keine neuen Spiele seit {prev['stamp']} ({n_played} gespielt)"
        automation_status.write_step("snapshot", True, msg, {
            "n_played": n_played,
            "changed": False,
            "derived_outputs_refreshed": True,
        })
        print(f"{msg} — kein neuer Snapshot.")
        return

    played_pairs = {frozenset(k) for k in fixed}    # gespielte Spiele -> Sperren verfallen
    susp_pair, susp_round = model.resolve_suspensions(played_pairs)
    random.seed()                                   # bewusst NICHT reproduzierbar fixiert
    titles = Counter()
    best = defaultdict(Counter)
    third_qual = Counter()          # wie oft qualifiziert sich t als einer der 8 besten Dritten
    rank = {r: i for i, r in enumerate(model.ROUNDS)}
    for _ in range(sims):
        go = {}
        champ, reached = model.simulate_tournament(
            groups, scores, group_out=go, fixed_group=fixed, ko_winners=ko,
            susp_pair=susp_pair, susp_round=susp_round, fairplay=fairplay)
        titles[champ] += 1
        for t, r in reached.items():
            best[t][r] += 1
        for t in go.get("_q3", ()):
            third_qual[t] += 1

    def p_at_least(t, rname):
        thr = rank[rname]
        return sum(c for r, c in best[t].items() if rank[r] >= thr) / sims

    def advanced_count(t):     # rohe Zahl: wie oft kam t aus der Gruppe (R32)?
        thr = rank["Sechzehntelfinale"]
        return sum(c for r, c in best[t].items() if rank[r] >= thr)

    # offiziell ausgeschieden = in KEINEM einzigen der Sims aus der Gruppe gekommen
    # (mathematisch chancenlos; nur sinnvoll, sobald Spiele gespielt sind)
    eliminated = {t: (n_played > 0 and advanced_count(t) == 0) for t in teams}

    snap = {
        "stamp": stamp, "n_played": n_played, "last_game": last_date or None,
        "n_sims": sims, "modus": modus, "live_eval": ev,
        "teams": {t: {"p_titel": round(titles[t] / sims, 4),
                      "p_finale": round(p_at_least(t, "Finale"), 4),
                      "p_halbfinale": round(p_at_least(t, "Halbfinale"), 4),
                      "p_achtelfinale": round(p_at_least(t, "Achtelfinale"), 4),
                      "elo": elo_now.get(t)} for t in teams},
    }
    fname = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(os.path.join(SNAP_DIR, fname), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    # Konditionierte Live-Wahrscheinlichkeiten fuers Dashboard (eigene Datei, damit
    # model.py weiterhin die statische win_probabilities_2026.csv besitzt).
    live = os.path.join(model._HERE, "..", "output", "live_probabilities.csv")
    with open(live, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "p_titel", "p_finale", "p_halbfinale", "p_achtelfinale",
                    "staerke_score", "elo", "eliminated", "n_played", "stamp"])
        for t, d in snap["teams"].items():
            w.writerow([t, d["p_titel"], d["p_finale"], d["p_halbfinale"],
                        d["p_achtelfinale"], round(scores[t], 4),
                        d["elo"], int(eliminated[t]), n_played, stamp])

    # --- Tabelle der besten Dritten (provisorisch nach gespielten Spielen) ---
    # Pro Gruppe die aktuelle Tabelle aus den gespielten Spielen (FIFA-2026-Rang),
    # der aktuelle Dritte; dann die 12 Dritten quergruppen ranken (Punkte -> Tordiff
    # -> Tore -> Fair-Play; KEIN h2h, da verschiedene Gruppen). Top 8 = Qualifikation.
    thirds = []
    for L, members in groups.items():
        st = {t: {"pts": 0, "gf": 0, "ga": 0, "pl": 0} for t in members}
        res = {}
        for (a, b), (ga, gb) in fixed.items():
            if a in st and b in st:
                res[(a, b)] = (ga, gb)
                st[a]["gf"] += ga; st[a]["ga"] += gb; st[a]["pl"] += 1
                st[b]["gf"] += gb; st[b]["ga"] += ga; st[b]["pl"] += 1
                if ga > gb:   st[a]["pts"] += 3
                elif gb > ga: st[b]["pts"] += 3
                else:         st[a]["pts"] += 1; st[b]["pts"] += 1
        t3 = model.rank_group(members, st, res, fairplay)[2]    # aktueller Gruppendritter
        s = st[t3]
        thirds.append({"group": L, "team": t3, "pts": s["pts"], "pl": s["pl"],
                       "gd": s["gf"] - s["ga"], "gf": s["gf"],
                       "p_qualify": round(third_qual[t3] / sims, 4)})
    thirds.sort(key=lambda d: (d["pts"], d["gd"], d["gf"], fairplay.get(d["team"], 0)),
                reverse=True)
    for idx, d in enumerate(thirds):
        d["qualified"] = idx < 8                                 # 8 beste Dritte ziehen ein
    with open(os.path.join(model._HERE, "..", "output", "thirds.json"), "w",
              encoding="utf-8") as f:
        json.dump({"stamp": stamp, "n_played": n_played, "thirds": thirds},
                  f, ensure_ascii=False, indent=1)

    hist = os.path.join(SNAP_DIR, "history.csv")
    new_hist = not os.path.exists(hist)
    with open(hist, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_hist:
            w.writerow(["stamp", "n_played", "team", "p_titel", "p_halbfinale", "elo"])
        for t, d in snap["teams"].items():
            w.writerow([stamp, n_played, t, d["p_titel"], d["p_halbfinale"], d["elo"]])

    print(f"\nSnapshot {stamp}  |  {n_played} WM-Spiele gespielt"
          + (f" (letztes: {last_date})" if last_date else " (Baseline vor Turnierstart)"))
    top = sorted(snap["teams"].items(), key=lambda kv: -kv[1]["p_titel"])[:8]
    if prev:
        print(f"\n{'Team':<14}{'Titel':>8}{'Δ':>8}   (vs. {prev['stamp']})")
        movers = sorted(snap["teams"],
                        key=lambda t: -abs(snap["teams"][t]["p_titel"]
                                           - prev["teams"].get(t, {}).get("p_titel", 0)))
        shown = [t for t, _ in top] + [t for t in movers[:5] if t not in dict(top)]
        for t in shown:
            p = snap["teams"][t]["p_titel"]
            d = p - prev["teams"].get(t, {}).get("p_titel", 0)
            mark = " ⚡AUSBRUCH" if abs(d) >= 0.03 else (" ▲" if d > 0.005 else " ▼" if d < -0.005 else "")
            print(f"{nice(t):<14}{p:>8.1%}{d:>+8.1%}{mark}")
    else:
        print(f"\n{'Team':<14}{'Titel':>8}{'Halbf.':>8}")
        for t, d in top:
            print(f"{nice(t):<14}{d['p_titel']:>8.1%}{d['p_halbfinale']:>8.1%}")
    if ev.get("gruppe"):
        g = ev["gruppe"]
        tag = "✅ schlaegt Basis" if g["logloss"] < g["basis"] else "❌ hinter Basis"
        print(f"\nLive-Check Vorturnier-Modell (Gruppenspiele, n={g['n']}): "
              f"LogLoss {g['logloss']:.3f} vs. Basis {g['basis']:.3f}  {tag}")
    if ev.get("ko"):
        k = ev["ko"]
        print(f"Live-Check K.-o. (n={k['n']}): {k['logloss']:.3f} vs. Muenzwurf 0.693")
    print(f"\nGespeichert: snapshots/{fname}  (+ history.csv)")
    automation_status.write_step("snapshot", True, f"Snapshot geschrieben: {fname}", {
        "n_played": n_played,
        "last_game": last_date or None,
        "changed": True,
    })


if __name__ == "__main__":
    main()
