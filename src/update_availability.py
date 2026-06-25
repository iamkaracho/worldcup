#!/usr/bin/env python3
"""
Availability-/Verletzungs-Update fuer data/injuries_2026.json.

Das Modell erwartet bereits data/injuries_2026.json. Dieses Skript automatisiert die
Datei, sobald ein kuratierter JSON-Feed gesetzt ist:

  AVAILABILITY_JSON_URL=https://.../availability.json python3 update_availability.py

Erwartetes Feed-Format ist bewusst identisch zu injuries_2026.json:
{
  "Deutschland": [{"player": "Name", "value": 40, "status": "out"}],
  "Spanien": [{"player": "Name", "value": 20, "status": "doubtful"}]
}

Ohne URL laeuft es als Validator/No-op. So bleibt die Pipeline cloudfaehig, ohne
eine fragile News-Scraping-Abhaengigkeit einzubauen.
"""

import json
import os
import urllib.request

import automation_status
import model


URL = os.environ.get("AVAILABILITY_JSON_URL") or os.environ.get("INJURIES_JSON_URL")
VALID_STATUS = {"out", "doubtful"}


def load_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "worldcup-model/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize(data):
    teams = set(model.load_teams(model.TEAMS_PATH))
    out = {
        "_comment": ("Automatisch aus AVAILABILITY_JSON_URL erzeugt. status: out voll, "
                     "doubtful zu 50%; value in Mio EUR."),
        "_source": {"url": URL},
    }
    errors = []
    for team, players in data.items():
        if team.startswith("_"):
            continue
        if team not in teams:
            errors.append(f"unbekanntes Team: {team}")
            continue
        clean = []
        for p in players:
            player = str(p.get("player", "")).strip()
            status = str(p.get("status", "out")).strip()
            if not player:
                errors.append(f"{team}: Spieler ohne Namen")
                continue
            if status not in VALID_STATUS:
                errors.append(f"{team}/{player}: ungueltiger status {status}")
                continue
            try:
                value = float(p.get("value", 0))
            except (TypeError, ValueError):
                errors.append(f"{team}/{player}: value ist keine Zahl")
                continue
            clean.append({"player": player, "value": value, "status": status})
        if clean:
            out[team] = clean
    if errors:
        raise ValueError("; ".join(errors))
    return out


def validate_existing():
    data = model._load_json(model.INJURIES_PATH) or {}
    normalize({k: v for k, v in data.items() if not k.startswith("_")})


def main():
    if not URL:
        validate_existing()
        msg = "keine AVAILABILITY_JSON_URL gesetzt; vorhandene Ausfall-Datei validiert"
        automation_status.write_step("availability", True, msg, {"mode": "validate-only"})
        print(msg)
        return
    try:
        data = normalize(load_url(URL))
        with open(model.INJURIES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        teams = len([k for k in data if not k.startswith("_")])
        players = sum(len(v) for k, v in data.items() if not k.startswith("_"))
        msg = f"Ausfaelle aktualisiert: {players} Spieler in {teams} Teams"
        automation_status.write_step("availability", True, msg, {
            "mode": "json-url",
            "teams": teams,
            "players": players,
        })
        print(msg)
    except Exception as exc:
        automation_status.write_step("availability", False, str(exc), {"mode": "json-url"})
        raise


if __name__ == "__main__":
    main()

