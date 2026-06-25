#!/usr/bin/env python3
"""
Automatisches Karten-/Sperren-Update fuer die WM-Pipeline.

Ohne API_FOOTBALL_KEY laeuft das Skript bewusst als Validator/No-op, damit lokale
Laeufe und Forks nicht brechen. Mit API_FOOTBALL_KEY nutzt es API-Sports/API-Football:

  API_FOOTBALL_KEY=... python3 update_cards.py

Optionale ENV:
  API_FOOTBALL_LEAGUE_ID   Default: 1
  API_FOOTBALL_SEASON      Default: 2026
  API_FOOTBALL_BASE_URL    Default: https://v3.football.api-sports.io

Die Modelllogik bleibt in model.py: Dieses Skript befuellt nur data/cards_2026.json.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

import automation_status
import calibrate
import model


BASE_URL = os.environ.get("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
LEAGUE_ID = os.environ.get("API_FOOTBALL_LEAGUE_ID", "1")
SEASON = os.environ.get("API_FOOTBALL_SEASON", "2026")
KEY = os.environ.get("API_FOOTBALL_KEY")
PLAYER_VALUES_PATH = os.path.join(model._HERE, "..", "data", "player_values_2026.json")

CARD_KEYS = ("yellow", "yellow_red", "red", "yellow_plus_red")


def api_get(path, params):
    url = BASE_URL.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(f"API error for {path}: {data['errors']}")
    return data.get("response", [])


def de_team(name):
    if not name:
        return None
    if name in calibrate.EN2DE:
        return calibrate.EN2DE[name]
    if name in calibrate.ALIASES:
        return name
    lowered = name.lower()
    for de, aliases in calibrate.ALIASES.items():
        if lowered == de.lower() or lowered in {a.lower() for a in aliases}:
            return de
    return None


def load_existing():
    data = model._load_json(model.CARDS_PATH) or {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_player_values():
    data = model._load_json(PLAYER_VALUES_PATH) or {}
    out = {}
    for team, players in data.items():
        out[team] = {p.lower(): float(v) for p, v in players.items()}
    return out


def player_value(values, team, player):
    if not player:
        return 0.0
    return values.get(team, {}).get(player.lower(), 0.0)


def fixture_dates():
    fixtures = model._load_json(model.FIXTURES_PATH) or []
    dates = sorted({x["date"] for x in fixtures})
    if not dates:
        return None, None
    return dates[0], dates[-1]


def fetch_fixture_ids():
    start, end = fixture_dates()
    params = {"league": LEAGUE_ID, "season": SEASON}
    if start and end:
        params["from"], params["to"] = start, end
    fixtures = api_get("/fixtures", params)
    out = []
    for f in fixtures:
        fix = f.get("fixture", {})
        teams = f.get("teams", {})
        home = de_team((teams.get("home") or {}).get("name"))
        away = de_team((teams.get("away") or {}).get("name"))
        if home and away:
            out.append({
                "id": fix.get("id"),
                "date": (fix.get("date") or "")[:10],
                "home": home,
                "away": away,
            })
    return [f for f in out if f["id"]]


def card_kind(detail):
    d = (detail or "").lower()
    if "second" in d and "yellow" in d:
        return "yellow_red"
    if "yellow" in d and "red" in d:
        return "yellow_red"
    if "red" in d:
        return "red"
    if "yellow" in d:
        return "yellow"
    return None


def build_cards_from_api():
    values = load_player_values()
    counts = defaultdict(lambda: {k: 0 for k in CARD_KEYS})
    bans = defaultdict(list)
    fixture_count = event_count = 0

    for fx in fetch_fixture_ids():
        fixture_count += 1
        events = api_get("/fixtures/events", {"fixture": fx["id"]})
        for ev in events:
            if ev.get("type") != "Card":
                continue
            team = de_team((ev.get("team") or {}).get("name"))
            if not team:
                continue
            kind = card_kind(ev.get("detail"))
            if not kind:
                continue
            event_count += 1
            counts[team][kind] += 1
            if kind in ("red", "yellow_red", "yellow_plus_red"):
                player = (ev.get("player") or {}).get("name") or "Unbekannt"
                minute = (ev.get("time") or {}).get("elapsed")
                label = f"{player} ({ev.get('detail')} vs {fx['away'] if team == fx['home'] else fx['home']}"
                if minute:
                    label += f", {minute}."
                label += ")"
                bans[team].append({
                    "player": label,
                    "value": player_value(values, team, player),
                    "after": fx["date"],
                    "games": 1,
                    "source": "api-football",
                })

    teams = model.load_teams(model.TEAMS_PATH)
    out = {
        "_comment": ("Automatisch aus API-Football Events erzeugt. Ohne Player-Wert in "
                     "data/player_values_2026.json wirkt eine Sperre nur ueber Fair-Play, "
                     "nicht ueber Staerke-Malus."),
        "_source": {
            "provider": "api-football",
            "league": LEAGUE_ID,
            "season": SEASON,
            "fixtures": fixture_count,
            "card_events": event_count,
        },
    }
    for team in teams:
        rec = {k: int(counts[team][k]) for k in CARD_KEYS if counts[team][k]}
        if bans[team]:
            rec["bans"] = bans[team]
        if rec:
            for k in CARD_KEYS:
                rec.setdefault(k, 0)
            out[team] = rec
    return out, fixture_count, event_count


def validate_cards(data):
    errors = []
    teams = set(model.load_teams(model.TEAMS_PATH))
    for team, rec in data.items():
        if team.startswith("_"):
            continue
        if team not in teams:
            errors.append(f"unbekanntes Team in cards_2026.json: {team}")
        for k in CARD_KEYS:
            if k in rec and int(rec[k]) < 0:
                errors.append(f"{team}.{k} ist negativ")
        for ban in rec.get("bans", []):
            if "value" not in ban:
                errors.append(f"{team} ban ohne value: {ban}")
            if "after" not in ban and "round" not in ban:
                errors.append(f"{team} ban ohne after/round: {ban}")
    return errors


def main():
    if "--validate-only" in sys.argv or not KEY:
        data = model._load_json(model.CARDS_PATH) or {}
        errors = validate_cards(data)
        if errors:
            automation_status.write_step("cards", False, "; ".join(errors))
            raise SystemExit("\n".join(errors))
        msg = "kein API_FOOTBALL_KEY gesetzt; vorhandene Karten-Datei validiert"
        automation_status.write_step("cards", True, msg, {"mode": "validate-only"})
        print(msg)
        return

    try:
        data, n_fixtures, n_events = build_cards_from_api()
        errors = validate_cards(data)
        if errors:
            raise RuntimeError("; ".join(errors))
        with open(model.CARDS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        msg = f"Karten aktualisiert: {n_events} Events aus {n_fixtures} Fixtures"
        automation_status.write_step("cards", True, msg, {
            "mode": "api-football",
            "fixtures": n_fixtures,
            "events": n_events,
        })
        print(msg)
    except Exception as exc:
        automation_status.write_step("cards", False, str(exc), {"mode": "api-football"})
        raise


if __name__ == "__main__":
    main()

