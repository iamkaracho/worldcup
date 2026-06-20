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
import model
import validate as V

SNAP_DIR = os.path.join(model._HERE, "..", "output", "snapshots")
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


def played_wc_games(rows, team2group):
    """(fixed_group, ko_winners, n_played, letzte_datum)"""
    pens = shootout_winners()
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
        if team2group.get(h) == team2group.get(a):          # Gruppenspiel
            fixed[(h, a)] = (hg, ag)
        else:                                               # K.-o.
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
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    rows = merge_manual(rows)

    fixed, ko, n_played, last_date = played_wc_games(rows, team2group)

    # Schon ein Snapshot mit diesem Stand? -> nichts zu tun.
    prev_files = sorted(f for f in os.listdir(SNAP_DIR) if f.startswith("snapshot_"))
    prev = None
    if prev_files:
        with open(os.path.join(SNAP_DIR, prev_files[-1]), encoding="utf-8") as f:
            prev = json.load(f)
    if prev and prev["n_played"] == n_played and not force:
        print(f"Keine neuen Spiele seit {prev['stamp']} ({n_played} gespielt) — kein neuer Snapshot.")
        return

    # Live-Validierung mit dem EINGEFRORENEN Vorturnier-Modell (vor Elo-Update!)
    frozen_scores, _ = model.build_scores(teams)
    ev = live_eval(fixed, ko, frozen_scores)

    # Elo frisch (Form!), Ausfaelle wie gehabt; Kalibrierung bleibt fix.
    elo_now = fresh_elo(rows)
    teams = {t: dict(v) for t, v in teams.items()}
    for t in teams:
        if t in elo_now:
            teams[t]["elo"] = elo_now[t]
    scores, modus = model.build_scores(teams)

    played_pairs = {frozenset(k) for k in fixed}    # gespielte Spiele -> Sperren verfallen
    susp_pair, susp_round = model.resolve_suspensions(played_pairs)
    fairplay = model.load_cards()
    random.seed()                                   # bewusst NICHT reproduzierbar fixiert
    titles = Counter()
    best = defaultdict(Counter)
    rank = {r: i for i, r in enumerate(model.ROUNDS)}
    for _ in range(sims):
        champ, reached = model.simulate_tournament(
            groups, scores, fixed_group=fixed, ko_winners=ko,
            susp_pair=susp_pair, susp_round=susp_round, fairplay=fairplay)
        titles[champ] += 1
        for t, r in reached.items():
            best[t][r] += 1

    def p_at_least(t, rname):
        thr = rank[rname]
        return sum(c for r, c in best[t].items() if rank[r] >= thr) / sims

    def advanced_count(t):     # rohe Zahl: wie oft kam t aus der Gruppe (R32)?
        thr = rank["Sechzehntelfinale"]
        return sum(c for r, c in best[t].items() if rank[r] >= thr)

    # offiziell ausgeschieden = in KEINEM einzigen der Sims aus der Gruppe gekommen
    # (mathematisch chancenlos; nur sinnvoll, sobald Spiele gespielt sind)
    eliminated = {t: (n_played > 0 and advanced_count(t) == 0) for t in teams}

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
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


if __name__ == "__main__":
    main()
