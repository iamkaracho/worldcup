#!/usr/bin/env python3
"""
Kalibrierungs-Check ohne externe Daten: Momentenabgleich.

Misst, welche *emergenten* Spielkennzahlen das Tormodell erzeugt, und vergleicht
sie mit bekannten WM-Basisraten. Wenn Tore/Spiel und Remisquote grob stimmen,
sind MU/BETA zumindest fussballerisch plausibel (notwendig, nicht hinreichend).

Reale WM-Richtwerte (Gruppenphase + gesamt):
  - Tore pro Spiel (beide Teams):  ~2.5 - 2.8   (WM 2022: 2.69)
  - Remis nach 90 Min (Gruppe):    ~25% - 33%
"""

import random
import model

N_TOURNAMENTS = 3000


def main():
    teams = model.load_teams(model.TEAMS_PATH)
    groups = model.load_groups(model.GROUPS_PATH)
    random.seed(model.SEED)
    scores, modus = model.build_scores(teams)

    rec = {"games": 0, "goals": 0, "draws": 0, "fav_games": 0, "fav_wins": 0}
    orig = model.match_goals

    def wrapped(a, b):
        ga, gb = orig(a, b)
        rec["games"] += 1
        rec["goals"] += ga + gb
        if ga == gb:
            rec["draws"] += 1
        elif scores[a] != scores[b]:
            rec["fav_games"] += 1
            fav, fg = (a, ga) if scores[a] > scores[b] else (b, gb)
            opp_g = gb if fav == a else ga
            if fg > opp_g:
                rec["fav_wins"] += 1
        return ga, gb

    model.match_goals = wrapped
    for _ in range(N_TOURNAMENTS):
        model.simulate_tournament(groups, scores)
    model.match_goals = orig

    g = rec["games"]
    print(f"Momentenabgleich  |  {modus}  |  MU_eff={model._MU_EFF:.2f} "
          f"GAMMA={model._GAMMA:.2f}  ({N_TOURNAMENTS:,} Turniere, {g:,} Spiele)\n")
    print(f"  Tore/Spiel (beide Teams) : {rec['goals']/g:5.2f}   "
          f"Zielband ~2.5-2.8")
    print(f"  Remisquote (alle Spiele) : {rec['draws']/g:5.1%}   "
          f"Zielband ~25-33% (Gruppe)")
    print(f"  Favoritensiegquote*      : {rec['fav_wins']/rec['fav_games']:5.1%}   "
          f"(*nur entschiedene Spiele)")
    print("\nLiegen Tore/Spiel oder Remisquote daneben -> MU/BETA anpassen.")


if __name__ == "__main__":
    main()
