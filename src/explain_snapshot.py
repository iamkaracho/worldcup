#!/usr/bin/env python3
"""
Erzeugt eine kurze taegliche Modell-Erklaerung aus Snapshot-Historie und Live-Stand.

Kein LLM, keine externe Abhaengigkeit: nur deterministische Saetze aus den Modellartefakten.
Schreibt output/snapshot_explain.json fuer dashboard.py.
"""

import csv
import json
import os
from collections import defaultdict

import model


HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "output")
SNAP_DIR = os.path.join(OUT, "snapshots")
OUT_PATH = os.path.join(OUT, "snapshot_explain.json")

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def pct(p):
    return f"{p * 100:.1f}%"


def pp(d):
    return f"{d * 100:+.1f} Pkt."


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_snapshots():
    files = sorted(f for f in os.listdir(SNAP_DIR) if f.startswith("snapshot_"))
    if not files:
        return None, None
    latest = json.load(open(os.path.join(SNAP_DIR, files[-1]), encoding="utf-8"))
    prev = None
    if len(files) > 1:
        prev = json.load(open(os.path.join(SNAP_DIR, files[-2]), encoding="utf-8"))
    return latest, prev


def last_history_pair():
    path = os.path.join(SNAP_DIR, "history.csv")
    if not os.path.exists(path):
        return None, None
    rows = read_csv(path)
    stamps = sorted({r["stamp"] for r in rows})
    if len(stamps) < 2:
        return None, None
    by = defaultdict(dict)
    for r in rows:
        by[r["stamp"]][r["team"]] = r
    return by[stamps[-1]], by[stamps[-2]]


def load_live_rows():
    path = os.path.join(OUT, "live_probabilities.csv")
    if not os.path.exists(path):
        return {}
    return {r["team"]: r for r in read_csv(path)}


def movement_reasons(team, cur, prev, live):
    reasons = []
    try:
        elo_delta = float(cur.get("elo") or 0) - float(prev.get("elo") or 0)
    except (TypeError, ValueError):
        elo_delta = 0
    if abs(elo_delta) >= 8:
        reasons.append(f"Live-Elo {elo_delta:+.0f}")
    if live.get(team, {}).get("eliminated") == "1":
        reasons.append("ausgeschieden")
    p8 = float(live.get(team, {}).get("p_achtelfinale") or 0)
    if p8 == 0:
        reasons.append("kein Gruppenweg mehr")
    elif p8 > 0.70:
        reasons.append("Gruppenweg fast offen")
    elif p8 < 0.10:
        reasons.append("Gruppenweg eng")
    return reasons[:2] or ["Bracket und Restfeld"]


def build():
    latest, prev_snap = latest_snapshots()
    cur_hist, prev_hist = last_history_pair()
    live = load_live_rows()
    if not latest:
        payload = {"available": False, "headline": "Noch kein Snapshot vorhanden.", "movers": []}
    else:
        movers = []
        if cur_hist and prev_hist:
            teams = sorted(cur_hist, key=lambda t: abs(float(cur_hist[t]["p_titel"])
                                                       - float(prev_hist.get(t, {}).get("p_titel", 0))),
                           reverse=True)
            for t in teams[:6]:
                cur = cur_hist[t]
                old = prev_hist.get(t, {})
                delta = float(cur["p_titel"]) - float(old.get("p_titel", 0))
                if abs(delta) < 0.001:
                    continue
                movers.append({
                    "team": t,
                    "name": nice(t),
                    "p_titel": round(float(cur["p_titel"]), 4),
                    "delta": round(delta, 4),
                    "direction": "up" if delta > 0 else "down",
                    "reasons": movement_reasons(t, cur, old, live),
                })
        top = sorted(latest["teams"].items(), key=lambda kv: -kv[1]["p_titel"])[:3]
        leader = top[0][0]
        ev = latest.get("live_eval", {}).get("gruppe")
        check = None
        if ev:
            check = {
                "n": ev["n"],
                "logloss": ev["logloss"],
                "basis": ev["basis"],
                "beats_basis": ev["logloss"] < ev["basis"],
            }
        if movers:
            main = movers[0]
            headline = (f"{main['name']} bewegt sich am staerksten: {pp(main['delta'])} "
                        f"auf {pct(main['p_titel'])} Titelchance.")
        else:
            headline = "Keine grossen Spruenge: der neue Snapshot bestaetigt den Vortag."
        payload = {
            "available": True,
            "stamp": latest["stamp"],
            "n_played": latest["n_played"],
            "last_game": latest.get("last_game"),
            "leader": {"team": leader, "name": nice(leader), "p_titel": top[0][1]["p_titel"]},
            "top3": [{"team": t, "name": nice(t), "p_titel": d["p_titel"]} for t, d in top],
            "headline": headline,
            "movers": movers,
            "live_eval": check,
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Snapshot-Erklaerung geschrieben: {os.path.relpath(OUT_PATH, HERE)}")


if __name__ == "__main__":
    build()

