#!/usr/bin/env python3
"""
Kostenlose Karten-Stufe aus oeffentlichen Quellen.

Ziel: sichere ROTE Karten/Sperren ohne Paid API automatisch in cards_2026.json mergen.
Gelbe Karten werden hier bewusst NICHT automatisch aus News/Wiki abgeleitet, weil fuer
den Fair-Play-Tiebreaker Vollstaendigkeit wichtiger ist als eine halbe Liste.

Quellen:
  - Wikipedia/MediaWiki: List_of_FIFA_World_Cup_red_cards
  - Wikipedia/MediaWiki: 2026_FIFA_World_Cup (Discipline-/Suspension-Tabellen, falls da)

Output:
  - data/raw/cards_public_candidates.json  (alles, was gefunden wurde)
  - data/cards_2026.json                   (nur sichere neue rote Karten/Bans)
"""

import hashlib
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import automation_status
import calibrate
import model
import update_cards


API = "https://en.wikipedia.org/w/api.php"
RAW_OUT = os.path.join(model._HERE, "..", "data", "raw", "cards_public_candidates.json")
SOURCES = [
    ("world_cup_red_cards", "List_of_FIFA_World_Cup_red_cards"),
    ("world_cup_2026", "2026_FIFA_World_Cup"),
]
MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._table = []
        self._row = []
        self._cell = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
            self._table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row = []
        elif self._in_row and tag in ("td", "th"):
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            text = html.unescape(" ".join("".join(self._cell).split()))
            self._row.append(text)
            self._cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(self._row):
                self._table.append(self._row)
            self._row = []
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._table:
                self.tables.append(self._table)
            self._table = []
            self._in_table = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def wiki_html(page):
    params = {
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "worldcup-model/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(f"MediaWiki error for {page}: {data['error']}")
    return data["parse"]["text"], "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page)


def parse_tables(page):
    text, url = wiki_html(page)
    p = TableParser()
    p.feed(text)
    return p.tables, url


def iso_date(text):
    m = re.search(r"\b(2026)-(\d{2})-(\d{2})\b", text)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(2026)\b", text)
    if m:
        mon = MONTHS.get(m.group(2).lower())
        if mon:
            return f"2026-{mon}-{int(m.group(1)):02d}"
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),\s*(2026)\b", text)
    if m:
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            return f"2026-{mon}-{int(m.group(2)):02d}"
    return None


def de_team(text):
    clean = re.sub(r"\[[^\]]+\]", "", text or "").strip()
    if clean in calibrate.EN2DE:
        return calibrate.EN2DE[clean]
    if clean in calibrate.ALIASES:
        return clean
    low = clean.lower()
    for de, aliases in calibrate.ALIASES.items():
        names = {de.lower(), *(a.lower() for a in aliases)}
        if low in names:
            return de
    return None


def likely_player(cells, teams):
    noise = {"2026", "fifa world cup", "first round", "group stage", "round of 32",
             "round of 16", "quarter-finals", "semi-finals", "final"}
    for c in cells:
        t = re.sub(r"\([^)]*\)", "", c).strip()
        tl = t.lower()
        if not t or any(n in tl for n in noise):
            continue
        if iso_date(t) or re.search(r"\d+\s*[-–]\s*\d+", t):
            continue
        if de_team(t) or t in teams:
            continue
        words = [w for w in re.split(r"\s+", t) if w]
        if 1 <= len(words) <= 5 and any(ch.isalpha() for ch in t):
            return t
    return "Unbekannt"


def source_id(c):
    raw = "|".join(str(c.get(k, "")) for k in ("source", "team", "player", "after", "opponent"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def norm_text(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def same_player(a, b):
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    last_a = na.split()[-1] if na.split() else ""
    last_b = nb.split()[-1] if nb.split() else ""
    if len(last_a) > 4 and last_a in wb:
        return True
    if len(last_b) > 4 and last_b in wa:
        return True
    return bool(wa & wb) and (wa <= wb or wb <= wa or len(wa & wb) >= 2)


def row_candidate(source_name, source_url, row, page):
    text = " | ".join(row)
    low = text.lower()
    if "2026" not in text:
        return None
    if page == "2026_FIFA_World_Cup" and not any(w in low for w in ("red", "suspension", "sent off")):
        return None
    teams = [t for t in (de_team(c) for c in row) if t]
    if not teams:
        return None
    team = teams[0]
    opponent = teams[1] if len(teams) > 1 and teams[1] != team else None
    after = iso_date(text)
    player = likely_player(row, set(teams))
    confidence = 0.76 if page == "List_of_FIFA_World_Cup_red_cards" else 0.64
    if after and player != "Unbekannt":
        confidence += 0.12
    if opponent:
        confidence += 0.04
    candidate = {
        "source": source_name,
        "source_url": source_url,
        "team": team,
        "opponent": opponent,
        "player": player,
        "after": after,
        "kind": "red",
        "games": 1,
        "confidence": round(min(confidence, 0.95), 2),
        "raw": text,
    }
    candidate["id"] = source_id(candidate)
    return candidate


def collect_candidates():
    out = []
    errors = []
    for source_name, page in SOURCES:
        try:
            tables, url = parse_tables(page)
            for table in tables:
                for row in table[1:]:
                    c = row_candidate(source_name, url, row, page)
                    if c:
                        out.append(c)
        except Exception as exc:
            errors.append(f"{page}: {exc}")
    seen = set()
    unique = []
    for c in out:
        if c["id"] not in seen:
            unique.append(c)
            seen.add(c["id"])
    return unique, errors


def merge_safe(candidates):
    data = model._load_json(model.CARDS_PATH) or {}
    if "_comment" not in data:
        data["_comment"] = "Karten und Sperren fuer das WM-Modell."
    data["_public_sources"] = {
        "note": "Sichere rote Karten werden aus oeffentlichen Quellen gemerged; Gelbe bleiben manuell/offiziell.",
        "candidates": os.path.relpath(RAW_OUT, os.path.join(model._HERE, "..")),
    }

    applied = 0
    for c in candidates:
        if c.get("confidence", 0) < 0.84 or not c.get("after") or not c.get("team"):
            continue
        team = c["team"]
        rec = data.setdefault(team, {})
        bans = rec.setdefault("bans", [])
        if any(b.get("source_id") == c["id"] for b in bans):
            continue
        if any(same_player(c["player"], b.get("player", "")) and b.get("after") == c["after"]
               for b in bans):
            continue
        # Falls die Datei bereits manuell kumulierte rote Karten fuer das Team enthaelt,
        # zaehlen wir nicht noch einmal hoch. Die Public-Stufe ergaenzt dann nur die
        # konkrete Sperre. Bei komplett neuen Teams erzeugt sie den Fair-Play-Zaehler.
        if not any(int(rec.get(k, 0)) for k in ("red", "yellow_red", "yellow_plus_red")):
            rec["red"] = 1
        rec.setdefault("yellow", 0)
        rec.setdefault("red", int(rec.get("red", 0)))
        rec.setdefault("yellow_red", 0)
        rec.setdefault("yellow_plus_red", 0)
        label = c["player"]
        if c.get("opponent"):
            label += f" (rot vs {c['opponent']})"
        ban = {
            "player": label,
            "value": update_cards.player_value(update_cards.load_player_values(), team, c["player"]),
            "after": c["after"],
            "games": c.get("games", 1),
            "source": c["source_url"],
            "source_id": c["id"],
        }
        bans.append(ban)
        applied += 1

    errors = update_cards.validate_cards(data)
    if errors:
        raise RuntimeError("; ".join(errors))
    with open(model.CARDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return applied


def main():
    no_fetch = "--no-fetch" in sys.argv
    apply = "--apply" in sys.argv or "--apply-safe" in sys.argv
    if no_fetch:
        candidates = model._load_json(RAW_OUT) or []
        errors = []
    else:
        candidates, errors = collect_candidates()
        os.makedirs(os.path.dirname(RAW_OUT), exist_ok=True)
        with open(RAW_OUT, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    applied = merge_safe(candidates) if apply else 0
    ok = not errors
    msg = f"oeffentliche Kartenquellen: {len(candidates)} Kandidaten, {applied} gemerged"
    if errors:
        msg += " (" + "; ".join(errors) + ")"
    automation_status.write_step("cards_public", ok, msg, {
        "mode": "public-sources",
        "candidates": len(candidates),
        "applied": applied,
        "candidate_file": os.path.relpath(RAW_OUT, os.path.join(model._HERE, "..")),
    })
    print(msg)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
