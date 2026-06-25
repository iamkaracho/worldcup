#!/usr/bin/env python3
"""
Belastung / Reise / Klima-Kontext fuer offene Gruppenspiele.

Das ist bewusst ein Sensitivitaets-/Dashboard-Artefakt, kein kalibriertes Feature:
Resttage sind sicher aus dem Spielplan ableitbar; Venue/Klima/Reise werden nur genutzt,
wenn results.csv die Stadt liefert. Output: output/context_factors.json.
"""

import csv
import json
import math
import os
from datetime import date

import calibrate
import model
import snapshot


OUT_PATH = os.path.join(model._HERE, "..", "output", "context_factors.json")

HOST_CITY = {
    "Atlanta": (33.75, -84.39, "warm"),
    "Boston": (42.36, -71.06, "mild"),
    "Dallas": (32.78, -96.80, "hot"),
    "Guadalajara": (20.67, -103.35, "altitude"),
    "Houston": (29.76, -95.37, "hot-humid"),
    "Kansas City": (39.10, -94.58, "warm"),
    "Los Angeles": (34.05, -118.24, "mild"),
    "Miami": (25.76, -80.19, "hot-humid"),
    "Monterrey": (25.69, -100.32, "hot"),
    "New York": (40.71, -74.01, "mild"),
    "New York New Jersey": (40.81, -74.07, "mild"),
    "Philadelphia": (39.95, -75.17, "warm"),
    "San Francisco": (37.77, -122.42, "mild"),
    "San Francisco Bay Area": (37.40, -121.98, "mild"),
    "Seattle": (47.61, -122.33, "mild"),
    "Toronto": (43.65, -79.38, "mild"),
    "Vancouver": (49.28, -123.12, "mild"),
    "Mexico City": (19.43, -99.13, "altitude"),
    "Ciudad de Mexico": (19.43, -99.13, "altitude"),
    "Zapopan": (20.72, -103.40, "altitude"),
}


NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}


def nice(t):
    return NICE.get(t, t)


def parse_date(s):
    return date.fromisoformat(s)


def km(a, b):
    if not a or not b:
        return None
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def rows_with_manual():
    has_results = os.path.exists(calibrate.RESULTS_PATH)
    rows = list(csv.DictReader(open(calibrate.RESULTS_PATH, encoding="utf-8"))) if has_results else []
    return snapshot.merge_manual(rows), has_results


def live_n_played():
    path = os.path.join(model._HERE, "..", "output", "live_probabilities.csv")
    if not os.path.exists(path):
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return int(rows[0].get("n_played") or 0) if rows else 0


def fixture_meta(rows):
    out = {}
    for r in rows:
        if r.get("date", "") < "2026-06-01" or "World Cup" not in r.get("tournament", ""):
            continue
        h, a = calibrate.EN2DE.get(r["home_team"]), calibrate.EN2DE.get(r["away_team"])
        if not h or not a:
            continue
        city = r.get("city") or ""
        out[(r["date"], h, a)] = {
            "city": city,
            "country": r.get("country") or "",
            "coord": HOST_CITY.get(city, (None, None, None))[:2] if city in HOST_CITY else None,
            "climate": HOST_CITY.get(city, (None, None, "unknown"))[2] if city in HOST_CITY else "unknown",
        }
    return out


def played_games(rows, team2group):
    fixed, _, n, _ = snapshot.played_wc_games(rows, team2group)
    return fixed, n


def last_played_info(fixtures, fixed):
    info = {}
    for f in sorted(fixtures, key=lambda x: x["date"]):
        a, b = f["home"], f["away"]
        if (a, b) in fixed or (b, a) in fixed:
            for t in (a, b):
                info[t] = {"date": f["date"], "city": f.get("city"), "coord": f.get("coord")}
    return info


def rest_label(days):
    if days is None:
        return "unbekannt"
    if days <= 3:
        return "kurze Pause"
    if days >= 6:
        return "lange Pause"
    return "normal"


def build():
    rows, has_results = rows_with_manual()
    groups = model.load_groups(model.GROUPS_PATH)
    team2group = {t: g for g, ms in groups.items() for t in ms}
    fixed, n_played = played_games(rows, team2group)
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
        print(f"Kontextfaktoren uebersprungen: {payload['reason']}")
        return
    meta = fixture_meta(rows)
    raw = model._load_json(model.FIXTURES_PATH) or []
    fixtures = []
    for f in raw:
        m = meta.get((f["date"], f["home"], f["away"])) or {}
        fixtures.append({**f, **m})
    fixtures.sort(key=lambda x: (x["date"], x["group"]))
    last = last_played_info(fixtures, fixed)
    games = []
    for f in fixtures:
        a, b = f["home"], f["away"]
        if (a, b) in fixed or (b, a) in fixed:
            continue
        cur_date = parse_date(f["date"])
        teams = []
        for t in (a, b):
            prev = last.get(t)
            days = (cur_date - parse_date(prev["date"])).days if prev else None
            travel = km(prev.get("coord") if prev else None, f.get("coord"))
            burden = 0
            if days is not None and days <= 3:
                burden += 2
            elif days is not None and days <= 4:
                burden += 1
            if travel is not None and travel >= 2500:
                burden += 2
            elif travel is not None and travel >= 1200:
                burden += 1
            if f.get("climate") in ("hot", "hot-humid", "altitude"):
                burden += 1
            teams.append({
                "team": t,
                "name": nice(t),
                "rest_days": days,
                "rest_label": rest_label(days),
                "travel_km": round(travel) if travel is not None else None,
                "burden": burden,
            })
        games.append({
            "group": f["group"],
            "date": f["date"],
            "city": f.get("city") or None,
            "climate": f.get("climate") or "unknown",
            "home": a,
            "away": b,
            "home_name": nice(a),
            "away_name": nice(b),
            "teams": teams,
        })

    payload = {
        "n_played": n_played,
        "available": bool(games),
        "note": "Sensitivitaets-Kontext, nicht kalibriert.",
        "games": games,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Kontextfaktoren geschrieben: {os.path.relpath(OUT_PATH, model._HERE)} ({len(games)} Spiele)")


if __name__ == "__main__":
    build()
