#!/usr/bin/env python3
"""
Vollstaendiges WM-2026-Modell nach Klement (Rekonstruktionsanalyse).

Pipeline (vgl. MODELLPLANUNG.md):

    48 Teams x 4 Variablen
      -> log/z-Standardisierung
      -> Staerke-Score  S_i = w . x_i        (Variablen 1-4)
      -> Poisson-Tormodell je Spiel          (Zufallsfaktor = inhaerent stochastisch)
      -> Gruppenphase (12 Gruppen a 4, je 6 Spiele)
      -> Qualifikation: 2 pro Gruppe + 8 beste Gruppendritte = 32
      -> K.-o.-Baum: Sechzehntel -> Achtel -> Viertel -> Halb -> Finale
         (Unentschieden in K.o. -> Elfmeter via logistischem Zufall)
      -> Monte-Carlo (N Laeufe) -> P(Weltmeister) etc.

Bewusst nur Python-Standardbibliothek (kein numpy/yaml noetig).
Daten in ../data sind ILLUSTRATIV; Variable 3 = Kader-Marktwert-Proxy.
"""

import csv
import json
import math
import os
import random
from collections import Counter, defaultdict

# --- Konfiguration -----------------------------------------------------------

WEIGHTS = {
    "bip_pc":       0.8,   # 1 Wohlstand / Infrastruktur
    "bevoelkerung": 0.6,   # 2 Bevoelkerungsgroesse
    "marktwert":    1.0,   # 3 Verankerung des Fussballs (Marktwert-Proxy)
    "fifa_punkte":  1.6,   # 4 Position Weltrangliste
    "elo":          1.4,   # 5 World-Football-Elo (eloratings.net-Methode) <- ergebnisbasiert
}
LOG_VARS = {"bip_pc", "bevoelkerung", "marktwert"}

# Tormodell: lambda_i = MU * exp(+BETA*(S_i-S_j)/2), lambda_j = MU * exp(-...).
# MU   ~ mittlere Tore pro Team und Spiel.
# BETA = Steilheit (klein -> mehr Zufall/Ueberraschungen; gross -> Favorit dominiert).
# Heuristik-Defaults (Fallback, falls keine Kalibrierung vorliegt):
MU = 1.25    # momentenkalibriert: ~2.66 Tore/Spiel (vgl. WM 2022: 2.69), s. calib_check.py
BETA = 0.45  # Steilheit im Fallback-Modus
# (Elfmeter/Verlaengerung werden ueber die halbe Tormodell-Steilheit modelliert.)

# Kalibrierte Parameter (aus calibrate.py). Wenn die Datei existiert, ueberschreibt
# sie WEIGHTS/MU datenbasiert und das Modell laeuft im Modus "kalibriert".
CALIB_PATH = None  # wird unten gesetzt
# Heimvorteil der Gastgeber (USA/Mexiko/Kanada), in log-Tor-Einheiten je Heimspiel.
# None -> gefitteten Heimvorteil aus der Kalibrierung nutzen; Zahl -> fester Wert; 0 -> aus.
HOST_BONUS = None
HOSTS = {"USA", "Mexiko", "Kanada"}

N_SIMS = 20_000
SEED = 7  # Reproduzierbarkeit; fuer echte Laeufe auf None setzen.

_HERE = os.path.dirname(__file__)
TEAMS_PATH = os.path.join(_HERE, "..", "data", "teams_2026.csv")
GROUPS_PATH = os.path.join(_HERE, "..", "data", "groups_2026.json")
OUT_PATH = os.path.join(_HERE, "..", "output", "win_probabilities_2026.csv")
CALIB_PATH = os.path.join(_HERE, "..", "data", "calibrated_params.json")
RATINGS_PATH = os.path.join(_HERE, "..", "data", "team_ratings.json")
INJURIES_PATH = os.path.join(_HERE, "..", "data", "injuries_2026.json")
CARDS_PATH = os.path.join(_HERE, "..", "data", "cards_2026.json")
FIXTURES_PATH = os.path.join(_HERE, "..", "output", "group_fixtures.json")

# Effektive Tormodell-Parameter, werden von build_scores() gesetzt:
#   lambda_i = _MU_EFF * exp((_ATT[i] - _DEF[j]) [+ _HOST_ADV falls i Gastgeber])
#   _RHO = Dixon-Coles-Korrektur. _ATT/_DEF tragen den Massstab (kalibriert _GAMMA=1).
_MU_EFF = MU
_GAMMA = BETA / 2
_RHO = 0.0
_HOST_ADV = 0.0
_ATT = {}
_DEF = {}
# Kontext fuer Sperren-Deltas (von build_scores gesetzt): injury-bereinigte Marktwerte,
# log-Marktwert-Streuung des Feldes und die kalibrierten Marktwert-Gewichte att/def.
_SUSP_CTX = None

ROUNDS = ["Gruppenphase", "Sechzehntelfinale", "Achtelfinale",
          "Viertelfinale", "Halbfinale", "Finale", "Weltmeister"]


# --- 1. Daten ----------------------------------------------------------------

def load_teams(path):
    teams = {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    header = rows[0]
    for row in rows[1:]:
        rec = dict(zip(header, row))
        teams[rec["team"]] = {k: float(v) for k, v in rec.items() if k != "team"}
    return teams


def load_groups(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


# --- 2./3. Standardisierung + Staerke-Score ----------------------------------

def standardized_features(teams):
    """{team: {var: z-Wert}} — log-Transform (fuer LOG_VARS) + z-Standardisierung.

    Gemeinsame Basis fuer Staerke-Score (model) und Poisson-Regression (calibrate),
    damit beide exakt dieselben Feature-Werte verwenden.
    """
    feats = {t: dict(v) for t, v in teams.items()}
    for var in WEIGHTS:
        vals = []
        for t in feats:
            x = math.log(feats[t][var]) if var in LOG_VARS else feats[t][var]
            feats[t][var] = x
            vals.append(x)
        mean = sum(vals) / len(vals)
        sd = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5 or 1.0
        for t in feats:
            feats[t][var] = (feats[t][var] - mean) / sd
    return feats


def _load_json(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def load_calibration():
    return _load_json(CALIB_PATH)


def load_ratings():
    return _load_json(RATINGS_PATH)


def load_injuries():
    """{team: abzuziehender Marktwert} aus den bekannten Ausfaellen.
    'out' voll, 'doubtful' zu 50%. Leeres dict, wenn keine Datei."""
    data = _load_json(INJURIES_PATH) or {}
    out = {}
    for team, players in data.items():
        if team.startswith("_"):
            continue
        out[team] = sum(p["value"] * (0.5 if p.get("status") == "doubtful" else 1.0)
                        for p in players)
    return out


# FIFA-Fair-Play-Punkte je Karte (negativ = schlechter).
_FAIRPLAY_PTS = {"yellow": 1, "yellow_red": 3, "red": 4, "yellow_plus_red": 5}


def load_cards():
    """{team: Fair-Play-Punkte (<=0)} aus data/cards_2026.json.
    Vorletztes FIFA-Gruppen-Tiebreaker-Kriterium (nach Direktvergleich, vor Losentscheid).
    Nur fuer GESPIELTE Spiele bekannt -> verbessert die Aufloesung gegenueber Zufall."""
    data = _load_json(CARDS_PATH) or {}
    out = {}
    for team, c in data.items():
        if team.startswith("_"):
            continue
        out[team] = -sum(_FAIRPLAY_PTS[k] * c.get(k, 0) for k in _FAIRPLAY_PTS)
    return out


def suspension_delta(team, value):
    """(d_att, d_def) <= 0: um wie viel sinken Angriff/Abwehr eines Teams, wenn ein
    gesperrter Spieler im Wert `value` (Mio) fehlt. Nutzt EXAKT die Modell-Kalibrierung
    (log-Marktwert-z * att/def-Marktwert-Gewicht), Feld-Streuung fix (Marginalnaeherung).
    build_scores() muss vorher gelaufen sein (setzt _SUSP_CTX)."""
    ctx = _SUSP_CTX
    if not ctx or team not in ctx["mw"]:
        return (0.0, 0.0)
    mw = ctx["mw"][team]
    dz = (math.log(max(1.0, mw - value)) - math.log(max(1.0, mw))) / ctx["logsd"]
    return (ctx["att_w"] * dz, ctx["def_w"] * dz)


def _group_schedule():
    """{datum: [(heim_de, ausw_de), ...]} der Gruppenspiele aus group_fixtures.json."""
    fx = _load_json(FIXTURES_PATH)
    sched = {}
    if fx:
        for x in fx:
            sched.setdefault(x["date"], []).append((x["home"], x["away"]))
    return sched


def resolve_suspensions(played=None):
    """Leitet Sperren aus den `bans` in cards_2026.json ab und mappt sie auf Spiele:
      susp_pair  : {frozenset({a,b}): {team: (d_att,d_def)}}  (naechstes Gruppenspiel)
      susp_round : {rundenname:        {team: (d_att,d_def)}}  (K.-o. per Runde)
    Eine Sperre {value, after} trifft AUTOMATISCH das naechste noch nicht gespielte
    Gruppenspiel des Teams nach `after` und verfaellt von selbst, sobald es gespielt ist
    (`played` = Menge bereits gespielter frozenset-Paarungen, vom Live-Treiber gereicht).
    Mehrere Sperren desselben Teams im selben Spiel werden aufaddiert.
    build_scores() muss vorher gelaufen sein."""
    data = _load_json(CARDS_PATH) or {}
    sched = _group_schedule()
    fixtures = {}                                 # team -> sortiert [(datum, gegner, paar)]
    for d, pairs in sorted(sched.items()):
        for h, a in pairs:
            fixtures.setdefault(h, []).append((d, a, frozenset((h, a))))
            fixtures.setdefault(a, []).append((d, h, frozenset((h, a))))
    played = played or set()
    susp_pair, susp_round = {}, {}

    def _add(store, key, team, dlt):
        store.setdefault(key, {})
        p = store[key].get(team, (0.0, 0.0))
        store[key][team] = (p[0] + dlt[0], p[1] + dlt[1])

    for team, c in data.items():
        if team.startswith("_"):
            continue
        for ban in c.get("bans", []):
            dlt = suspension_delta(team, ban["value"])
            if ban.get("round"):
                _add(susp_round, ban["round"], team, dlt)
                continue
            after = ban.get("after", "0000-00-00")
            games = ban.get("games", 1)           # i.d.R. 1 Spiel (rote Karte)
            # die naechsten `games` Spiele nach dem Vergehen; abgesessene (gespielte)
            # verfallen, es wird NICHT auf spaetere Spiele weitergerollt.
            upcoming = [f for f in fixtures.get(team, []) if f[0] > after][:games]
            for f in upcoming:
                if f[2] not in played:
                    _add(susp_pair, f[2], team, dlt)
    return susp_pair, susp_round


def _apply_calib(calib, feats):
    """Setzt _ATT/_DEF/_MU_EFF/_RHO aus einem Kalibrier-Dict (single oder att/def).
    Gibt die Netto-Staerke (scores) zurueck. Gemeinsam genutzt von build_scores
    und uncertainty.py (Bootstrap)."""
    global _MU_EFF, _GAMMA, _RHO, _ATT, _DEF
    _MU_EFF, _GAMMA, _RHO = math.exp(calib["mu"]), 1.0, calib.get("rho", 0.0)
    if "att_weights" in calib:
        aw, dw = calib["att_weights"], calib["def_weights"]
        _ATT = {t: sum(aw[v] * feats[t][v] for v in aw) for t in feats}
        _DEF = {t: sum(dw[v] * feats[t][v] for v in dw) for t in feats}
        # Gesamtstaerke vs. Durchschnittsgegner: gut im Angriff UND in der Abwehr
        scores = {t: _ATT[t] + _DEF[t] for t in feats}
    else:
        W = calib["weights"]
        scores = {t: sum(W[v] * feats[t][v] for v in W) for t in feats}
        _ATT = dict(scores); _DEF = dict(scores)
    return scores


def build_scores(teams, use_ratings=True, apply_injuries=True):
    """Liefert (scores, modus). Setzt die globalen Tormodell-Parameter und _ATT/_DEF.

    Modus-Prioritaet (bestes zuerst):
    - rating-basiert : Team-Rating (Ergebnisse + Klement-Prior).
    - kalibriert     : Poisson-Regression; entweder Einzelstaerke oder Angriff/Abwehr.
    - heuristisch    : score auf Einheitsstreuung normiert (Fallback).
    Tormodell: lambda_i = _MU_EFF * exp((_ATT[i]-_DEF[j]) [+ Heimvorteil]).
    apply_injuries: zieht bekannte Ausfaelle vom Kader-Marktwert ab (Prognose-Seite).
    """
    global _MU_EFF, _GAMMA, _RHO, _HOST_ADV, _ATT, _DEF, _SUSP_CTX
    inj = load_injuries() if apply_injuries else {}
    if inj:
        teams = {t: dict(v) for t, v in teams.items()}
        for t, cut in inj.items():
            if t in teams:
                teams[t]["marktwert"] = max(1.0, teams[t]["marktwert"] - cut)
    feats = standardized_features(teams)
    ratings = load_ratings() if use_ratings else None
    _RHO, home_coef = 0.0, 0.0

    if ratings and all(t in ratings["ratings"] for t in feats):
        scores = {t: ratings["ratings"][t] for t in feats}
        _MU_EFF, _GAMMA = math.exp(ratings["mu"]), 1.0
        home_coef = ratings.get("eta", 0.0)
        _ATT = dict(scores); _DEF = dict(scores)
        modus = f"rating-basiert (+Klement-Prior, rho={ratings.get('rho','?')})"
    elif load_calibration():
        calib = load_calibration()
        scores = _apply_calib(calib, feats)
        home_coef = calib.get("home", 0.0)
        mtag = f", {calib.get('model','att/def')}" if "att_weights" in calib else ""
        modus = (f"kalibriert (n={calib.get('n_matches','?')} Spiele{mtag}"
                 + (f", DC rho={_RHO:+.3f}" if _RHO else "") + ")")
    else:
        raw = {t: sum(WEIGHTS[v] * feats[t][v] for v in WEIGHTS) for t in feats}
        mean = sum(raw.values()) / len(raw)
        sd = (sum((x - mean) ** 2 for x in raw.values()) / len(raw)) ** 0.5 or 1.0
        scores = {t: (raw[t] - mean) / sd for t in raw}
        _MU_EFF, _GAMMA = MU, BETA / 2
        _ATT = {t: _GAMMA * scores[t] for t in scores}   # att=def -> reproduziert Single
        _DEF = dict(_ATT)
        modus = "heuristisch (unkalibriert)"

    _HOST_ADV = home_coef if HOST_BONUS is None else HOST_BONUS
    if _HOST_ADV:
        modus += f", Heimvorteil={_HOST_ADV:+.2f}"
    if inj:
        modus += f", inkl. Ausfälle ({len(inj)} Teams)"

    # Kontext fuer Sperren-Deltas: Marktwert-Gewichte aus der Kalibrierung + Feld-Streuung
    # des (injury-bereinigten) log-Marktwerts. Gleiche Basis wie die Staerke-Berechnung.
    cal = load_calibration() or {}
    if "att_weights" in cal:
        aw_mw, dw_mw = cal["att_weights"].get("marktwert", 0.0), cal["def_weights"].get("marktwert", 0.0)
    elif "weights" in cal:
        aw_mw = dw_mw = cal["weights"].get("marktwert", 0.0)
    else:
        aw_mw = dw_mw = WEIGHTS.get("marktwert", 1.0)
    logs = [math.log(max(1.0, teams[t]["marktwert"])) for t in teams]
    mean = sum(logs) / len(logs)
    sd = (sum((x - mean) ** 2 for x in logs) / len(logs)) ** 0.5 or 1.0
    _SUSP_CTX = {"mw": {t: teams[t]["marktwert"] for t in teams},
                 "logsd": sd, "att_w": aw_mw, "def_w": dw_mw}
    return scores, modus


def strength_scores(teams):
    """Rueckwaertskompatibel: nur die Scores."""
    return build_scores(teams)[0]


def strength_scores(teams):
    """Rueckwaertskompatibel: nur die Scores."""
    return build_scores(teams)[0]


# --- 4. Spiel-Modelle --------------------------------------------------------

def _poisson(lam):
    """Knuth-Algorithmus, ohne numpy."""
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def _dc_tau(i, j, lh, la, rho):
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def _lam(att_team, def_team, is_host, d_att=0.0, d_def=0.0):
    d = ((_ATT[att_team] + d_att) - (_DEF[def_team] + d_def)) + (_HOST_ADV if is_host else 0.0)
    return _MU_EFF * math.exp(max(-3.0, min(3.0, d)))


def _adj_pair(adj, a, b):
    """(d_att_a, d_def_a, d_att_b, d_def_b) aus einem optionalen {team: (d_att,d_def)}."""
    aa = adj.get(a, (0.0, 0.0)) if adj else (0.0, 0.0)
    bb = adj.get(b, (0.0, 0.0)) if adj else (0.0, 0.0)
    return aa[0], aa[1], bb[0], bb[1]


def match_goals(a, b, adj=None):
    da_a, dd_a, da_b, dd_b = _adj_pair(adj, a, b)
    lh = _lam(a, b, a in HOSTS, da_a, dd_b)      # a greift an: a-Angriffsmalus, b-Abwehrmalus
    la = _lam(b, a, b in HOSTS, da_b, dd_a)
    if _RHO == 0.0:
        return _poisson(lh), _poisson(la)
    # Dixon-Coles: exaktes Rejection-Sampling (Huelle = max der vier Korrekturen)
    tmax = max(1.0, 1.0 - lh * la * _RHO, 1.0 - _RHO)
    while True:
        i, j = _poisson(lh), _poisson(la)
        if random.random() < max(0.0, _dc_tau(i, j, lh, la, _RHO)) / tmax:
            return i, j


def match_probs(a, b, grid=11, adj=None):
    """Analytische Vorhersage eines Spiels a vs b (gleiche Lambdas wie match_goals).
    Liefert (P(a-Sieg), P(Remis), P(b-Sieg), wahrscheinlichstes (ga,gb), (lam_a,lam_b))."""
    da_a, dd_a, da_b, dd_b = _adj_pair(adj, a, b)
    la, lb = _lam(a, b, a in HOSTS, da_a, dd_b), _lam(b, a, b in HOSTS, da_b, dd_a)
    pa = [math.exp(-la) * la ** i / math.factorial(i) for i in range(grid)]
    pb = [math.exp(-lb) * lb ** j / math.factorial(j) for j in range(grid)]
    pw = pd = pl = tot = 0.0
    best, best_p = (0, 0), -1.0
    for i in range(grid):
        for j in range(grid):
            p = pa[i] * pb[j] * _dc_tau(i, j, la, lb, _RHO)
            tot += p
            if i > j:    pw += p
            elif i == j: pd += p
            else:        pl += p
            if p > best_p:
                best_p, best = p, (i, j)
    return pw / tot, pd / tot, pl / tot, best, (la, lb)


def score_distribution(a, b, top=6, grid=11, adj=None):
    """Exakte Ergebnis-Verteilung von a vs b. Liefert die `top` haeufigsten
    Ergebnisse als [(ga, gb, wahrscheinlichkeit), ...] absteigend."""
    da_a, dd_a, da_b, dd_b = _adj_pair(adj, a, b)
    la, lb = _lam(a, b, a in HOSTS, da_a, dd_b), _lam(b, a, b in HOSTS, da_b, dd_a)
    pa = [math.exp(-la) * la ** i / math.factorial(i) for i in range(grid)]
    pb = [math.exp(-lb) * lb ** j / math.factorial(j) for j in range(grid)]
    cells, tot = [], 0.0
    for i in range(grid):
        for j in range(grid):
            p = pa[i] * pb[j] * _dc_tau(i, j, la, lb, _RHO)
            cells.append((i, j, p)); tot += p
    cells.sort(key=lambda c: -c[2])
    return [(i, j, p / tot) for i, j, p in cells[:top]]


def knockout_winner(a, b, scores, adj=None):
    ga, gb = match_goals(a, b, adj)
    if ga > gb:
        return a
    if gb > ga:
        return b
    # Verlaengerung/Elfmeter -> nahezu Muenzwurf, nur leichter Edge fuer den Staerkeren.
    p = 1.0 / (1.0 + math.exp(-(scores[a] - scores[b]) / 4))
    return a if random.random() < p else b


# --- 5. Gruppenphase ---------------------------------------------------------

def _h2h(t, grp, res):
    """Direktvergleich von t gegen die anderen Teams in grp: (Punkte, Tordiff, Tore)."""
    pts = gd = gf = 0
    for o in grp:
        if o == t:
            continue
        if (t, o) in res:
            tg, og = res[(t, o)]
        elif (o, t) in res:
            og, tg = res[(o, t)]
        else:
            continue                 # noch nicht gegeneinander gespielt (Teiltabelle)
        gd += tg - og
        gf += tg
        pts += 3 if tg > og else 1 if tg == og else 0
    return pts, gd, gf


def play_group(members, scores, fixed=None, susp_pair=None, fairplay=None):
    """Round-Robin mit der NEUEN FIFA-2026-Tiebreaker-Reihenfolge:
    Punkte -> DIREKTVERGLEICH (Punkte/Tordiff/Tore unter den punktgleichen Teams)
    -> Gesamt-Tordiff -> Gesamttore -> Fair-Play -> (Rest: Zufall statt FIFA-Ranking,
    praktisch nie erreicht). WICHTIG: Direktvergleich kommt VOR der Gesamt-Tordifferenz
    (Umkehrung ggue. fruehern WMs; deshalb ist z.B. ein Team, das gegen beide Rivalen
    verlor, bei Punktgleichheit chancenlos, egal wie hoch es das letzte Spiel gewinnt).
    fixed: {(a,b): (ga,gb)} GESPIELTE Ergebnisse. susp_pair: Sperren-Malus je Spiel.
    fairplay: {team: Fair-Play-Punkte}."""
    stats = {t: {"pts": 0, "gf": 0, "ga": 0, "tb": random.random()} for t in members}
    fp = fairplay or {}
    res = {}
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            a, b = members[i], members[j]
            if fixed and (a, b) in fixed:
                ga, gb = fixed[(a, b)]
            elif fixed and (b, a) in fixed:
                gb, ga = fixed[(b, a)]
            else:
                adj = susp_pair.get(frozenset((a, b))) if susp_pair else None
                ga, gb = match_goals(a, b, adj)
            res[(a, b)] = (ga, gb)
            stats[a]["gf"] += ga; stats[a]["ga"] += gb
            stats[b]["gf"] += gb; stats[b]["ga"] += ga
            if ga > gb:
                stats[a]["pts"] += 3
            elif gb > ga:
                stats[b]["pts"] += 3
            else:
                stats[a]["pts"] += 1; stats[b]["pts"] += 1

    ranked = rank_group(members, stats, res, fp)
    return ranked, stats, res


def rank_group(members, stats, res, fairplay=None):
    """FIFA-2026-Rangfolge: Punkte -> DIREKTVERGLEICH (h2h-Pkt/Tordiff/Tore unter den
    Punktgleichen) -> Gesamt-Tordiff -> Gesamttore -> Fair-Play -> tb/FIFA-Ranking.
    Wiederverwendet von play_group UND der Dritten-Tabelle (eine einzige Tiebreaker-Logik).
    stats[t] braucht pts/gf/ga, optional tb; res = {(a,b):(ga,gb)} der gespielten Spiele."""
    fp = fairplay or {}

    def tiebreak(t, block):
        hp, hgd, hgf = _h2h(t, block, res)        # Direktvergleich unter den Punktgleichen
        return (hp, hgd, hgf,
                stats[t]["gf"] - stats[t]["ga"],  # dann Gesamt-Tordifferenz
                stats[t]["gf"],                   # dann Gesamttore
                fp.get(t, 0),                     # dann Fair-Play
                stats[t].get("tb", 0.0))          # Rest (FIFA-Ranking-Naeherung)

    order = sorted(members, key=lambda t: stats[t]["pts"], reverse=True)
    ranked, i = [], 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and stats[order[j + 1]]["pts"] == stats[order[i]]["pts"]:
            j += 1
        block = order[i:j + 1]
        if len(block) > 1:
            block = sorted(block, key=lambda t: tiebreak(t, block), reverse=True)
        ranked += block
        i = j + 1
    return ranked


def third_place_key(t, stats):
    s = stats[t]
    return (s["pts"], s["gf"] - s["ga"], s["gf"], s["tb"])


# --- 6. K.-o.-Baum -----------------------------------------------------------

# Offizieller WM-2026 K.-o.-Baum (FIFA-Spielnummern 73-104, Wikipedia/FIFA-Schema).
# Drittplatzierten-Slots: je Slot die laut Reglement (Annex C) erlaubten Gruppen.
THIRD_SLOTS = {74: set("ABCDF"), 77: set("CDFGH"), 79: set("CEFHI"),
               80: set("EHIJK"), 81: set("BEFIJ"), 82: set("AEHIJ"),
               85: set("EFGIJ"), 87: set("DEIJL")}

# R32-Paarungen: ('W',L)=Gruppensieger, ('R',L)=Gruppenzweiter, ('3',matchno)=zugeordneter Dritter
R32 = {73: (("R", "A"), ("R", "B")), 74: (("W", "E"), ("3", 74)),
       75: (("W", "F"), ("R", "C")), 76: (("W", "C"), ("R", "F")),
       77: (("W", "I"), ("3", 77)), 78: (("R", "E"), ("R", "I")),
       79: (("W", "A"), ("3", 79)), 80: (("W", "L"), ("3", 80)),
       81: (("W", "D"), ("3", 81)), 82: (("W", "G"), ("3", 82)),
       83: (("R", "K"), ("R", "L")), 84: (("W", "H"), ("R", "J")),
       85: (("W", "B"), ("3", 85)), 86: (("W", "J"), ("R", "H")),
       87: (("W", "K"), ("3", 87)), 88: (("R", "D"), ("R", "G"))}

# Spaetere Runden: Spielnummer -> (Kind-Spielnummer A, Kind-Spielnummer B)
TREE = {89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
        93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
        97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
        101: (97, 98), 102: (99, 100), 104: (101, 102)}

ROUND_OF = {**{m: "Sechzehntelfinale" for m in range(73, 89)},
            **{m: "Achtelfinale" for m in range(89, 97)},
            **{m: "Viertelfinale" for m in range(97, 101)},
            101: "Halbfinale", 102: "Halbfinale", 104: "Finale"}


def assign_thirds(qualified_letters):
    """Ordnet die 8 qualifizierten Gruppendritten ihren Slots zu (Bipartit-Matching
    unter den Annex-C-Constraints). Liefert {matchno: gruppenbuchstabe}."""
    slots = sorted(THIRD_SLOTS, key=lambda m: len(THIRD_SLOTS[m] & qualified_letters))
    result, used = {}, set()

    def backtrack(i):
        if i == len(slots):
            return True
        m = slots[i]
        for L in sorted(THIRD_SLOTS[m] & qualified_letters):
            if L in used:
                continue
            used.add(L); result[m] = L
            if backtrack(i + 1):
                return True
            used.discard(L); del result[m]
        return False

    if backtrack(0):
        return result
    # Fallback fuer (theoretisch) nicht zuordenbare Kombination:
    leftover = [L for L in qualified_letters if L not in result.values()]
    for m in slots:
        if m not in result:
            result[m] = leftover.pop()
    return result


def simulate_tournament(groups, scores, group_out=None, fixed_group=None, ko_winners=None,
                        susp_pair=None, susp_round=None, fairplay=None):
    """group_out (optional dict): wird je Gruppe mit der 4er-Rangliste befuellt,
    plus group_out['_q3'] = Menge der als Gruppendritte qualifizierten Teams.
    fixed_group: bereits gespielte Gruppenspiele {(a,b):(ga,gb)} (Conditioning).
    ko_winners: bereits entschiedene K.-o.-Spiele {frozenset({a,b}): sieger}.
    susp_pair/susp_round/fairplay: Sperren-Mali (Gruppe/K.-o.) und Fair-Play-Punkte."""
    reached = {t: "Gruppenphase" for g in groups.values() for t in g}
    W, R, third, tstats = {}, {}, {}, {}
    for letter, members in groups.items():
        ranked, stats, _ = play_group(members, scores, fixed_group, susp_pair, fairplay)
        W[letter], R[letter], third[letter] = ranked[0], ranked[1], ranked[2]
        tstats[letter] = stats
        reached[ranked[0]] = reached[ranked[1]] = "Sechzehntelfinale"
        if group_out is not None:
            group_out[letter] = list(ranked)

    q = set(sorted(groups, key=lambda L: third_place_key(third[L], tstats[L]),
                   reverse=True)[:8])           # 8 beste Gruppendritte
    for L in q:
        reached[third[L]] = "Sechzehntelfinale"
    if group_out is not None:
        group_out["_q3"] = {third[L] for L in q}
    slot_letter = assign_thirds(q)

    def spec_team(spec):
        kind, val = spec
        return W[val] if kind == "W" else R[val] if kind == "R" else third[slot_letter[val]]

    cache = {}

    def resolve(m):
        if m not in cache:
            if m in R32:
                a, b = spec_team(R32[m][0]), spec_team(R32[m][1])
            else:
                ca, cb = TREE[m]
                a, b = resolve(ca), resolve(cb)
            if ko_winners and frozenset((a, b)) in ko_winners:
                w = ko_winners[frozenset((a, b))]
            else:
                radj = susp_round.get(ROUND_OF[m]) if susp_round else None
                adj = {t: radj[t] for t in (a, b) if t in radj} if radj else None
                w = knockout_winner(a, b, scores, adj)
            reached[b if w == a else a] = ROUND_OF[m]
            cache[m] = w
        return cache[m]

    champ = resolve(104)
    reached[champ] = "Weltmeister"
    return champ, reached


# --- 7. Monte-Carlo ----------------------------------------------------------

def run(groups, scores, n=N_SIMS):
    titles = Counter()
    best_round = defaultdict(Counter)   # team -> {Runde: Anzahl}
    rank = {r: i for i, r in enumerate(ROUNDS)}
    susp_pair, susp_round = resolve_suspensions()
    fairplay = load_cards()
    for _ in range(n):
        champ, reached = simulate_tournament(groups, scores, susp_pair=susp_pair,
                                             susp_round=susp_round, fairplay=fairplay)
        titles[champ] += 1
        for t, r in reached.items():
            best_round[t][r] += 1
    return titles, best_round, rank


def prob_at_least(best_round, n, team, round_name, rank):
    """P(Team erreicht mindestens round_name)."""
    thr = rank[round_name]
    return sum(c for r, c in best_round[team].items() if rank[r] >= thr) / n


# --- Ausgabe -----------------------------------------------------------------

def main():
    if SEED is not None:
        random.seed(SEED)

    teams = load_teams(TEAMS_PATH)
    groups = load_groups(GROUPS_PATH)
    scores, modus = build_scores(teams)

    assert sum(len(g) for g in groups.values()) == 48, "Erwarte 48 Teams"

    print(f"WM-2026-Modell  |  48 Teams, {N_SIMS:,} Simulationen  |  Modus: {modus}")
    print(f"  Tormodell: lambda_i = {_MU_EFF:.2f} * exp(att_i - def_j"
          + (" + Heimvorteil" if _HOST_ADV else "") + ")")
    print("  Daten ILLUSTRATIV (Variablenwerte grob recherchiert).\n")

    print("--- Staerke-Score Top 12 ---")
    for t, s in sorted(scores.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {t:<20} {s:+.2f}")

    titles, best_round, rank = run(groups, scores)
    n = sum(titles.values())

    print(f"\n--- P(Weltmeister) Top 16 ---")
    for t, c in titles.most_common(16):
        bar = "#" * round(50 * c / n)
        print(f"  {t:<20} {c/n:6.1%}  {bar}")

    print("\n--- Schluesselteams (P erreicht mind. Runde) ---")
    hdr = f"  {'Team':<14}{'Achtel':>8}{'Viertel':>9}{'Halbf.':>8}{'Finale':>8}{'Titel':>8}"
    print(hdr)
    for t in ["Niederlande", "Deutschland", "Frankreich", "Spanien",
              "Argentinien", "England", "Brasilien"]:
        if t not in best_round:
            continue
        a, v, h, fi, ti = [prob_at_least(best_round, n, t, r, rank)
                            for r in ["Achtelfinale", "Viertelfinale", "Halbfinale",
                                      "Finale", "Weltmeister"]]
        print(f"  {t:<14}{a:>8.0%}{v:>9.0%}{h:>8.0%}{fi:>8.0%}{ti:>8.0%}")

    champ = titles.most_common(1)[0][0]
    print(f"\n>>> Modell-Favorit Weltmeister 2026: {champ} ({titles[champ]/n:.1%})")
    print("    (Artikel: Klement tippt die Niederlande.)")

    # Ergebnis sichern
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "staerke_score", "p_titel", "p_finale",
                    "p_halbfinale", "p_achtelfinale"])
        for t in sorted(titles | Counter(best_round.keys()), key=lambda x: -titles[x]):
            w.writerow([t, f"{scores[t]:.3f}", f"{titles[t]/n:.4f}",
                        f"{prob_at_least(best_round, n, t, 'Finale', rank):.4f}",
                        f"{prob_at_least(best_round, n, t, 'Halbfinale', rank):.4f}",
                        f"{prob_at_least(best_round, n, t, 'Achtelfinale', rank):.4f}"])
    print(f"\nDetail-Wahrscheinlichkeiten gespeichert: {os.path.relpath(OUT_PATH, _HERE)}")


if __name__ == "__main__":
    main()
