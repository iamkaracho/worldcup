#!/usr/bin/env python3
"""
Spielzustand / Incentives fuer offene Gruppenspiele.

Fuer jedes noch offene Gruppenspiel wird simuliert:
  P(Team kommt weiter | Sieg)
  P(Team kommt weiter | Remis)
  P(Team kommt weiter | Niederlage)

Das bildet auch das 48er-Format mit besten Dritten ab; harte Tabellenlogik allein
waere hier zu spröde. Output: output/match_incentives.json.
"""

import csv
import json
import os
import random
import sys

import calibrate
import model
import snapshot


OUT_PATH = os.path.join(model._HERE, "..", "output", "match_incentives.json")
N_SIMS = 1500

NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def read_rows():
    has_results = os.path.exists(calibrate.RESULTS_PATH)
    if has_results:
        rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8")))
    else:
        rows = []
    return snapshot.merge_manual(rows), has_results


def live_n_played():
    path = os.path.join(model._HERE, "..", "output", "live_probabilities.csv")
    if not os.path.exists(path):
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return int(rows[0].get("n_played") or 0) if rows else 0


def fixed_key(fixed, a, b):
    return (a, b) in fixed or (b, a) in fixed


def apply_live_elo(rows):
    teams = {t: dict(v) for t, v in model.load_teams(model.TEAMS_PATH).items()}
    for t, elo in snapshot.fresh_elo(rows).items():
        if t in teams:
            teams[t]["elo"] = elo
    return model.build_scores(teams)


def p_advance(team, groups, scores, fixed, ko, susp_pair, susp_round, fairplay, sims):
    rank = {r: i for i, r in enumerate(model.ROUNDS)}
    adv = 0
    for _ in range(sims):
        champ, reached = model.simulate_tournament(
            groups, scores, fixed_group=fixed, ko_winners=ko,
            susp_pair=susp_pair, susp_round=susp_round, fairplay=fairplay)
        if rank[reached[team]] >= rank["Sechzehntelfinale"]:
            adv += 1
    return adv / sims


def outcome_fixed(fixed, a, b, outcome_for_a):
    out = dict(fixed)
    if outcome_for_a == "win":
        out[(a, b)] = (1, 0)
    elif outcome_for_a == "draw":
        out[(a, b)] = (0, 0)
    else:
        out[(a, b)] = (0, 1)
    return out


def classify(pw, pd, pl):
    if pl >= 0.985:
        return "sicher weiter"
    if pw <= 0.015:
        return "praktisch raus"
    if pd >= 0.90 and pl < 0.65:
        return "Remis reicht fast sicher"
    if pd >= 0.75 and pl < 0.45:
        return "Remis waere viel wert"
    if pw >= 0.65 and pd < 0.35:
        return "muss gewinnen"
    if pw - pd >= 0.30:
        return "Sieg stark empfohlen"
    if pd - pl >= 0.30:
        return "Niederlage vermeiden"
    return "offen"


def team_record(team, a, probs):
    if team == a:
        pw, pd, pl = probs["win"], probs["draw"], probs["loss"]
    else:
        pw, pd, pl = probs["loss"], probs["draw"], probs["win"]
    return {
        "team": team,
        "name": nice(team),
        "p_if_win": round(pw, 4),
        "p_if_draw": round(pd, 4),
        "p_if_loss": round(pl, 4),
        "label": classify(pw, pd, pl),
    }


def build(sims=N_SIMS):
    rows, has_results = read_rows()
    groups = model.load_groups(model.GROUPS_PATH)
    team2group = {t: g for g, ms in groups.items() for t in ms}
    fixed, ko, n_played, last_date = snapshot.played_wc_games(rows, team2group)
    live_n = live_n_played()
    if not has_results and live_n > n_played:
        payload = {
            "available": False,
            "reason": ("data/raw/results.csv fehlt lokal; manual_results.csv ist aelter "
                       "als der vorhandene Live-Stand."),
            "n_played": n_played,
            "live_n_played": live_n,
            "games": [],
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print(f"Incentives uebersprungen: {payload['reason']}")
        return
    scores, modus = apply_live_elo(rows)
    played_pairs = {frozenset(k) for k in fixed}
    susp_pair, susp_round = model.resolve_suspensions(played_pairs)
    fairplay = model.load_cards()

    fixtures = model._load_json(model.FIXTURES_PATH) or []
    open_fx = [f for f in fixtures if not fixed_key(fixed, f["home"], f["away"])]
    # Fokus: unmittelbar kommende Spiele, aber alle offenen Gruppenspiele werden gespeichert.
    open_fx.sort(key=lambda f: (f["date"], f["group"]))
    random.seed(20260625)
    games = []
    for f in open_fx:
        a, b = f["home"], f["away"]
        probs = {}
        for outcome in ("win", "draw", "loss"):
            fx = outcome_fixed(fixed, a, b, outcome)
            probs[outcome] = p_advance(a, groups, scores, fx, ko, susp_pair, susp_round,
                                       fairplay, sims)
        games.append({
            "group": f["group"],
            "date": f["date"],
            "home": a,
            "away": b,
            "home_name": nice(a),
            "away_name": nice(b),
            "teams": [team_record(a, a, probs), team_record(b, a, probs)],
        })

    payload = {
        "n_played": n_played,
        "last_game": last_date or None,
        "n_sims": sims,
        "modus": modus,
        "games": games,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Incentives geschrieben: {os.path.relpath(OUT_PATH, model._HERE)} "
          f"({len(games)} offene Spiele, {sims} Sims je Outcome)")


def main():
    sims = int(sys.argv[sys.argv.index("--sims") + 1]) if "--sims" in sys.argv else N_SIMS
    build(sims)


if __name__ == "__main__":
    main()
