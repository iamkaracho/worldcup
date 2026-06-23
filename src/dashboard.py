#!/usr/bin/env python3
"""
Erzeugt ein eigenstaendiges, interaktives HTML-Dashboard aus den Modell-Outputs.

Liest: output/win_probabilities_2026.csv, output/title_uncertainty.csv,
       data/teams_2026.csv, data/groups_2026.json
Schreibt: output/dashboard.html  (offline lauffaehig, keine Abhaengigkeiten)

Nur Standardbibliothek. Nach jedem model.py-Lauf neu ausfuehren -> frisches Dashboard.
"""

import csv
import json
import os

_HERE = os.path.dirname(__file__)
OUT = os.path.join(_HERE, "..", "output")
DATA = os.path.join(_HERE, "..", "data")

FLAG = {
    "Mexiko": "🇲🇽", "Suedkorea": "🇰🇷", "Suedafrika": "🇿🇦", "Tschechien": "🇨🇿",
    "Kanada": "🇨🇦", "Schweiz": "🇨🇭", "Katar": "🇶🇦", "Bosnien-Herzegowina": "🇧🇦",
    "Brasilien": "🇧🇷", "Marokko": "🇲🇦", "Schottland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Haiti": "🇭🇹",
    "USA": "🇺🇸", "Paraguay": "🇵🇾", "Australien": "🇦🇺", "Tuerkei": "🇹🇷",
    "Deutschland": "🇩🇪", "Ecuador": "🇪🇨", "Curacao": "🇨🇼", "Elfenbeinkueste": "🇨🇮",
    "Niederlande": "🇳🇱", "Japan": "🇯🇵", "Tunesien": "🇹🇳", "Schweden": "🇸🇪",
    "Belgien": "🇧🇪", "Aegypten": "🇪🇬", "Iran": "🇮🇷", "Neuseeland": "🇳🇿",
    "Spanien": "🇪🇸", "Uruguay": "🇺🇾", "Saudi-Arabien": "🇸🇦", "Kap Verde": "🇨🇻",
    "Frankreich": "🇫🇷", "Norwegen": "🇳🇴", "Senegal": "🇸🇳", "Irak": "🇮🇶",
    "Argentinien": "🇦🇷", "Oesterreich": "🇦🇹", "Algerien": "🇩🇿", "Jordanien": "🇯🇴",
    "Portugal": "🇵🇹", "Kolumbien": "🇨🇴", "Usbekistan": "🇺🇿", "DR Kongo": "🇨🇩",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Kroatien": "🇭🇷", "Ghana": "🇬🇭", "Panama": "🇵🇦",
}

# Anzeigenamen (Umlaute zurueck)
NICE = {"Suedkorea": "Südkorea", "Suedafrika": "Südafrika", "Tuerkei": "Türkei",
        "Curacao": "Curaçao", "Elfenbeinkueste": "Elfenbeinküste", "Aegypten": "Ägypten",
        "Oesterreich": "Österreich"}

# Schmunzler je Team (dezent, im Klement-Geist)
JOKE = {
    "Brasilien": "Ewiger Favorit auf dem Papier, ewiger Tröster auf der Tribüne.",
    "England": "Kommt zuverlässig weit. Dann kommt das Elfmeterschießen.",
    "Deutschland": "Laut Baum im Achtelfinale gegen Frankreich. Badehose einpacken.",
    "Niederlande": "Klements Bauchgefühl: die stärkste Nation, die nie Weltmeister wurde — bei Holländern fast schon Tradition.",
    "Frankreich": "Teuerster Kader, höchste Quote. Das Modell ist auch nur ein Buchhalter.",
    "Argentinien": "Titelverteidiger. Das Modell verteilt trotzdem keine Vorschusslorbeeren.",
    "Norwegen": "Hat Haaland. Hat keine Gruppenphase überstanden, die man kennt.",
    "USA": "Heimvorteil eingerechnet. Den Rest macht hoffentlich die Stimmung.",
    "Mexiko": "Spielt zu Hause, kommt fast immer ins Achtelfinale — und dann?",
    "Schottland": "Erste WM seit Ewigkeiten. Allein dabei sein ist hier schon der Titel.",
    "Curacao": "150.000 Einwohner, eine WM-Teilnahme. Das ist die eigentliche Sensation.",
    "Spanien": "Tiki-Taka trifft Marktwert. Das Modell mag beides.",
    "Kroatien": "Wird unterschätzt, steht am Ende doch wieder im Halbfinale. Vielleicht.",
    "Italien": "Nicht dabei. Schon wieder. Wir erwähnen es nur.",
}

ORACLE = [
    "Das Orakel sagt: Setz dein Geld lieber auf ein gutes Frühstück.",
    "Wahrscheinlichkeit ist, wenn man trotzdem mitfiebert.",
    "Frankreich ist Favorit. Das war Brasilien auch — bei jeder WM seit 1998.",
    "Der Erfinder dieses Modells hält es selbst für Quatsch. Und lag dreimal richtig.",
    "Ein Tipp auf die Niederlande ist mutig. Genau wie ein Achtelfinale-Tipp auf Deutschland.",
    "Statistik kann nicht weinen. Du beim Elfmeterschießen schon.",
    "16 % für den Favoriten heißt: in 5 von 6 Universen gewinnt jemand anderes.",
    "Das Modell kennt keine Wadenzerrung in der 3. Gruppenpartie. Du bald schon.",
    "Heimvorteil eingebaut. Schiedsrichter-Verschwörungen nicht — die musst du dir selbst ausdenken.",
    "Wer auf Basis dieses Dashboards wettet, dem ist laut Erfinder 'nicht zu helfen'. Wir zitieren nur.",
    "Brasilien führt die Stärke an und gewinnt am Ende trotzdem nichts. Tradition ist Tradition.",
    "Das Bauchgefühl-o-Meter zeigt heute: 'Wird schon irgendwie.'",
    "Ein Modell ist wie ein Wetterbericht — nur dass dich keiner für den Regen verantwortlich macht.",
    "Wenn dein Team nicht in den Top 5 ist: Es gibt auch Universen, in denen es klappt. Nur nicht in vielen.",
]


# ESPN-Rankings (extern, manuell): Experten-Panel (20 Reporter) & Kader-Modell (Elo+Marktwert)
ESPN_EXPERT = {"Spanien": 1, "Frankreich": 2, "Argentinien": 3, "England": 4,
               "Brasilien": 5, "Portugal": 6, "Deutschland": 7, "Niederlande": 8,
               "Marokko": 9, "Norwegen": 10}
ESPN_SQUAD = {"Frankreich": 1, "Spanien": 2, "England": 3, "Portugal": 4,
              "Deutschland": 5, "Brasilien": 6, "Argentinien": 7}
ESPN_NOTES = {
    "Argentinien": "Elo (Form) hebt sie hoch — Experten geben recht, das reine Kadermodell nicht.",
    "Norwegen": "Experten sehen Haaland-Momentum, das Marktwert & Elo nicht abbilden.",
    "Deutschland": "Experten skeptisch wegen schwacher Club-Form der Stars.",
    "Marokko": "Geheimtipp der Experten; quantitativ etwas tiefer eingestuft.",
    "Niederlande": "Klements Tipp — Modell und Experten gleichermaßen nüchtern.",
    "Brasilien": "Auf dem Papier top, im Turnier seit 2002 ohne Titel.",
    "England": "Modell & Experten einig — der Rest ist Elfmeterschießen.",
}


# Anzeige (Flagge, Name) fuer Teams im Mythos-Check (auch Nicht-WM-2026-Teams)
EN_DISP = {
    "France": ("🇫🇷", "Frankreich"), "Netherlands": ("🇳🇱", "Niederlande"),
    "Colombia": ("🇨🇴", "Kolumbien"), "Croatia": ("🇭🇷", "Kroatien"),
    "Belgium": ("🇧🇪", "Belgien"), "Morocco": ("🇲🇦", "Marokko"),
    "Brazil": ("🇧🇷", "Brasilien"), "Spain": ("🇪🇸", "Spanien"),
    "Argentina": ("🇦🇷", "Argentinien"), "Poland": ("🇵🇱", "Polen"),
    "Wales": ("🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Wales"), "Qatar": ("🇶🇦", "Katar"),
    "Germany": ("🇩🇪", "Deutschland"), "Uruguay": ("🇺🇾", "Uruguay"),
    "Costa Rica": ("🇨🇷", "Costa Rica"),
}


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_RACE_COLORS = ["#39d98a", "#5b8cff", "#ffb547", "#ff6b81", "#b78cff",
                "#4dd0e1", "#f0e68c", "#9aa7c7"]


def _race_svg():
    """SVG-Liniendiagramm der Titelchancen ueber alle Snapshots (history.csv).
    Liefert Hinweis-HTML, solange weniger als 2 Snapshot-Staende existieren."""
    hist = os.path.join(OUT, "snapshots", "history.csv")
    if not os.path.exists(hist):
        return '<p class="muted">Erscheint nach dem ersten Spieltag (Snapshots laufen automatisch).</p>'
    rows = _read_csv(hist)
    stamps = sorted({r["stamp"] for r in rows})
    if len(stamps) < 2:
        return '<p class="muted">Erst ein Snapshot (Baseline) — die Kurven starten nach dem ersten Spieltag.</p>'
    xi = {s: i for i, s in enumerate(stamps)}
    series = {}
    for r in rows:
        series.setdefault(r["team"], {})[xi[r["stamp"]]] = float(r["p_titel"])
    top = sorted(series, key=lambda t: -series[t].get(len(stamps) - 1, 0))[:8]
    W, H, L, R, T, B = 860, 320, 46, 150, 14, 30
    ymax = max(max(series[t].values()) for t in top) * 1.15 or 0.01
    def X(i): return L + i * (W - L - R) / max(len(stamps) - 1, 1)
    def Y(p): return T + (H - T - B) * (1 - p / ymax)
    parts = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px;background:#161b2e;border-radius:12px">']
    for frac in (0, .25, .5, .75, 1):
        y = Y(ymax * frac)
        parts.append(f'<line x1="{L}" y1="{y:.0f}" x2="{W-R}" y2="{y:.0f}" stroke="#2a3354" stroke-width="1"/>'
                     f'<text x="{L-6}" y="{y+4:.0f}" fill="#8a98bf" font-size="11" text-anchor="end">{ymax*frac:.0%}</text>')
    for i, s in enumerate(stamps):
        if len(stamps) <= 12 or i % max(1, len(stamps) // 10) == 0 or i == len(stamps) - 1:
            parts.append(f'<text x="{X(i):.0f}" y="{H-8}" fill="#8a98bf" font-size="10" text-anchor="middle">{s[5:10]}</text>')
    for ci, t in enumerate(top):
        pts = " ".join(f"{X(i):.1f},{Y(series[t][i]):.1f}" for i in sorted(series[t]))
        c = _RACE_COLORS[ci % len(_RACE_COLORS)]
        last_i = max(series[t]); ly = Y(series[t][last_i])
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2.2"/>'
                     f'<circle cx="{X(last_i):.1f}" cy="{ly:.1f}" r="3" fill="{c}"/>'
                     f'<text x="{X(last_i)+7:.0f}" y="{ly+4:.0f}" fill="{c}" font-size="12">'
                     f'{NICE.get(t, t)} {series[t][last_i]:.0%}</text>')
    parts.append("</svg>")
    return "".join(parts)


def build():
    # Waehrend des Turniers die KONDITIONIERTE Live-Datei (vom Snapshot) bevorzugen,
    # sonst die statische Vorturnier-Prognose (von model.py).
    live_path = os.path.join(OUT, "live_probabilities.csv")
    static_path = os.path.join(OUT, "win_probabilities_2026.csv")
    live_rows = _read_csv(live_path) if os.path.exists(live_path) else []
    live_n = int(live_rows[0]["n_played"]) if live_rows else 0
    if live_n > 0:
        probs = {r["team"]: r for r in live_rows}
        stand = f"Live-Stand nach {live_n} Spielen ({live_rows[0]['stamp']})"
    else:
        probs = {r["team"]: r for r in _read_csv(static_path)}
        stand = "Vorturnier-Prognose (Stand vor Anpfiff)"
    band = {r["team"]: r for r in _read_csv(os.path.join(OUT, "title_uncertainty.csv"))}
    teams = _read_teams()
    with open(os.path.join(DATA, "groups_2026.json"), encoding="utf-8") as f:
        groups = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    injuries = {}
    ipath = os.path.join(DATA, "injuries_2026.json")
    if os.path.exists(ipath):
        with open(ipath, encoding="utf-8") as f:
            for t, pl in json.load(f).items():
                if not t.startswith("_"):
                    injuries[t] = [p["player"] + ("*" if p.get("status") == "doubtful" else "")
                                   for p in pl]

    myth = None
    mpath = os.path.join(OUT, "tournament_myth.json")
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            myth = json.load(f)
        for side in ("overperformers", "underperformers"):
            myth[side] = [{"flag": EN_DISP.get(t, ("🏳️", t))[0],
                           "name": EN_DISP.get(t, ("🏳️", t))[1], "beta": b}
                          for t, b in myth[side]]
    team2group = {t: g for g, ms in groups.items() for t in ms}

    # Tabelle der besten Dritten (vom Snapshot, nur live sinnvoll)
    thirds = []
    tpath = os.path.join(OUT, "thirds.json")
    if live_n > 0 and os.path.exists(tpath):
        with open(tpath, encoding="utf-8") as f:
            for d in json.load(f)["thirds"]:
                thirds.append({**d, "name": NICE.get(d["team"], d["team"]),
                               "flag": FLAG.get(d["team"], "🏳️")})

    rows = []
    for t, p in probs.items():
        b = band.get(t, {})
        tm = teams.get(t, {})
        rows.append({
            "team": NICE.get(t, t), "key": t, "flag": FLAG.get(t, "🏳️"),
            "group": team2group.get(t, "?"),
            "titel": float(p["p_titel"]), "finale": float(p["p_finale"]),
            "halb": float(p["p_halbfinale"]), "achtel": float(p["p_achtelfinale"]),
            "staerke": float(p["staerke_score"]),
            "lo": float(b.get("p_titel_5pct", 0)), "hi": float(b.get("p_titel_95pct", 0)),
            "marktwert": float(tm.get("marktwert", 0)), "fifa": float(tm.get("fifa_punkte", 0)),
            "elo": float(p.get("elo") or tm.get("elo", 0)),   # live-Elo wenn vorhanden
            "inj": injuries.get(t, []),
            "joke": JOKE.get(t, ""),
            # offiziell ausgeschieden: vom Snapshot bestimmt (in 0 Sims aus der Gruppe gekommen)
            "dead": str(p.get("eliminated", "0")) == "1",
        })
    rows.sort(key=lambda r: -r["titel"])

    # Aschenputtel-Daten: erwartete Aussenseiter im HF + Dark Horses 2026
    bystr = sorted(rows, key=lambda r: -r["staerke"])
    top8 = {r["key"] for r in bystr[:8]}
    exp_out_sf = sum(r["halb"] for r in rows if r["key"] not in top8)
    darkhorses = [{"flag": r["flag"], "name": r["team"], "titel": r["titel"],
                   "achtel": r["achtel"], "halb": r["halb"]}
                  for r in sorted((r for r in rows if r["titel"] < 0.03 and r["achtel"] > 0.30),
                                  key=lambda r: -r["achtel"])[:6]]
    fixtures = None
    fpath = os.path.join(OUT, "group_fixtures.json")
    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            fixtures = json.load(f)
        for x in fixtures:
            x["hf"], x["hn"] = FLAG.get(x["home"], "🏳️"), NICE.get(x["home"], x["home"])
            x["af"], x["an"] = FLAG.get(x["away"], "🏳️"), NICE.get(x["away"], x["away"])

    cinderella = None
    cpath = os.path.join(OUT, "cinderella_tail.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            cinderella = [{"flag": EN_DISP.get(c["team"], ("🏳️", c["team"]))[0],
                           "name": EN_DISP.get(c["team"], ("🏳️", c["team"]))[1],
                           "year": c["year"], "reached": c["reached"], "p_run": c["p_run"]}
                          for c in json.load(f)]

    payload = {
        "rows": rows,
        "groups": {g: [NICE.get(t, t) for t in ms] for g, ms in groups.items()},
        "oracle": ORACLE,
        "favorit": rows[0],
        "espn_expert": ESPN_EXPERT, "espn_squad": ESPN_SQUAD, "espn_notes": ESPN_NOTES,
        "myth": myth,
        "cinderella": cinderella, "darkhorses": darkhorses,
        "exp_out_sf": round(exp_out_sf, 2),
        "fixtures": fixtures,
        "thirds": thirds,
    }
    html = TEMPLATE.replace("/*DATA*/", json.dumps(payload, ensure_ascii=False))
    html = html.replace("/*RACE*/", _race_svg())
    html = html.replace("/*STAND*/", stand)
    out = os.path.join(OUT, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard geschrieben: {os.path.relpath(out, _HERE)}  ({len(rows)} Teams)")


def _read_teams():
    rows = [r for r in csv.reader(open(os.path.join(DATA, "teams_2026.csv"), encoding="utf-8"))
            if r and not r[0].startswith("#")]
    header = rows[0]
    return {r[0]: dict(zip(header, r)) for r in rows[1:]}


TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WM 2026 — Das Klement-Orakel</title>
<style>
  :root{
    --bg:#15110a; --bg2:#1c1710; --card:#211b12; --card2:#282013;
    --line:#392f1f; --text:#f4ecdd; --muted:#a89c84; --gold:#f3c14a;
    --gold-deep:#d6a338; --blue:#7fa0c4; --green:#57b88a; --red:#e07f8b;
    --ink:#1a140c;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
    --ease-out:cubic-bezier(.23,1,.32,1);
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1100px 600px at 78% -12%,#3a2a0f4d,transparent),
        radial-gradient(820px 520px at -5% 2%,#2a1c0a4d,transparent),var(--bg);
        color:var(--text);font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
        -webkit-font-smoothing:antialiased}
  .wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
  a{color:var(--blue)}
  h1,h2,h3{margin:0;font-family:var(--serif);font-weight:600;letter-spacing:-.01em}
  .muted{color:var(--muted)}
  .tnum{font-variant-numeric:tabular-nums}

  html{scroll-behavior:smooth}
  header.hero{padding:76px 0 16px}
  .kicker{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.24em;
    text-transform:uppercase;color:var(--gold)}

  nav.pill{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:50;
    display:flex;gap:2px;background:#15110acc;backdrop-filter:blur(14px);
    -webkit-backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:999px;
    padding:5px;max-width:calc(100vw - 24px);overflow-x:auto;scrollbar-width:none}
  nav.pill a{color:var(--muted);text-decoration:none;font-size:13px;font-weight:600;
    padding:7px 14px;border-radius:999px;white-space:nowrap;
    transition:color .15s ease,background .15s ease}
  @media(hover:hover) and (pointer:fine){
    nav.pill a:hover{color:var(--text);background:#ffffff10}
  }

  .ticker{margin:26px 0 2px;overflow:hidden;
    -webkit-mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent);
    mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)}
  .ticker-track{display:inline-flex;gap:34px;white-space:nowrap;padding-right:34px;
    animation:marquee 52s linear infinite;will-change:transform}
  .ticker-track span{font-size:13px;color:var(--muted)}
  .ticker-track b{color:var(--gold);font-variant-numeric:tabular-nums}
  @media(hover:hover){.ticker:hover .ticker-track{animation-play-state:paused}}
  @keyframes marquee{to{transform:translateX(-50%)}}

  body::after{content:"";position:fixed;inset:0;pointer-events:none;opacity:.045;z-index:60;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}

  .io{opacity:0;transform:translateY(12px)}
  .io.in{opacity:1;transform:none;
    transition:opacity .55s var(--ease-out),transform .55s var(--ease-out)}
  h1{font-size:clamp(34px,6vw,56px);margin:14px 0 8px;color:var(--text);font-weight:700;line-height:1.04}
  .sub{color:var(--muted);max-width:62ch;font-size:17px;line-height:1.55}
  .stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 16px;
    animation:rise .45s var(--ease-out) backwards}
  .stat:nth-child(2){animation-delay:45ms}.stat:nth-child(3){animation-delay:90ms}
  .stat:nth-child(4){animation-delay:135ms}.stat:nth-child(5){animation-delay:180ms}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}}
  .stat b{font-size:20px} .stat span{display:block;color:var(--muted);font-size:12px;margin-top:2px}

  .cards{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:22px 0}
  @media(max-width:720px){.cards{grid-template-columns:1fr}}
  .card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);
    border-radius:16px;padding:18px 20px}
  .card .k{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
  .card .big{font-size:22px;font-weight:800;margin:6px 0}
  .card.tip{border-color:color-mix(in oklab,var(--gold) 30%,transparent);
    background:linear-gradient(180deg,#2a2110,var(--card))}
  .card.brk{border-color:color-mix(in oklab,var(--blue) 34%,transparent)}

  .oracle{margin:6px 0 26px;background:var(--card);border:1px dashed var(--line);
    border-radius:16px;padding:18px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
  .oracle button{cursor:pointer;border:0;border-radius:12px;padding:12px 18px;font-weight:800;
    font-size:15px;color:var(--ink);background:var(--gold);box-shadow:0 6px 20px #00000040;
    transition:transform .15s var(--ease-out),box-shadow .15s var(--ease-out)}
  @media(hover:hover) and (pointer:fine){
    .oracle button:hover{transform:translateY(-2px);box-shadow:0 12px 28px #00000059}
  }
  .oracle button:active{transform:scale(.97)}
  #oracle-text{flex:1;min-width:240px;font-size:16px;font-style:italic;
    animation:oracle-in .3s var(--ease-out)}
  @keyframes oracle-in{from{opacity:0;filter:blur(3px)}}
  #oracle-text b{font-style:normal}

  .controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:8px 0 14px}
  .controls input,.controls select{background:var(--card);color:var(--text);border:1px solid var(--line);
    border-radius:10px;padding:10px 12px;font-size:14px;outline:none}
  .controls input:focus,.controls select:focus{border-color:var(--blue)}
  .seg{display:inline-flex;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
  .seg button{background:transparent;border:0;color:var(--muted);padding:9px 13px;cursor:pointer;font-size:13px;font-weight:600;
    transition:background .15s ease,color .15s ease,transform .12s var(--ease-out)}
  .seg button:active{transform:scale(.95)}
  .seg button.on{background:var(--gold);color:var(--ink);font-weight:800}

  table{width:100%;border-collapse:collapse}
  th,td{padding:11px 8px;text-align:left}
  thead th{position:sticky;top:0;background:var(--bg2);border-bottom:1px solid var(--line);
    font-size:12px;letter-spacing:.04em;color:var(--muted);text-transform:uppercase;cursor:pointer;user-select:none}
  thead th.r,td.r{text-align:right}
  tbody tr{border-bottom:1px solid var(--line)}
  tbody tr.main{cursor:pointer;transition:background .15s ease}
  @media(hover:hover) and (pointer:fine){
    tbody tr.main:hover{background:#2a2114aa}
  }
  tbody tr.dead .name,tbody tr.dead .rank{opacity:.5}
  .skull{margin-right:6px;font-size:14px;filter:grayscale(.2)}
  #thirds table{width:100%;max-width:680px;border-collapse:collapse;font-variant-numeric:tabular-nums}
  #thirds th{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);
    text-align:right;padding:6px 8px;border-bottom:1px solid var(--line)}
  #thirds th:nth-child(2){text-align:left}
  #thirds td{padding:7px 8px;text-align:right;border-bottom:1px solid #ffffff0d}
  #thirds td:nth-child(2){text-align:left;font-weight:600}
  #thirds tr.q td{background:color-mix(in oklab,var(--green) 8%,transparent)}
  #thirds tr.cut td{border-bottom:2px solid var(--gold)}
  #thirds .qbar{display:inline-block;width:54px;height:7px;background:var(--ink);
    border-radius:4px;overflow:hidden;vertical-align:middle;margin-right:6px}
  #thirds .qbar i{display:block;height:100%;background:var(--green)}
  #thirds .gtag{color:var(--gold);font-weight:800;font-size:12px}
  .rank{color:var(--muted);width:28px;font-weight:700}
  .top1 .rank{color:var(--gold)} .top2 .rank{color:#cdc3ac} .top3 .rank{color:#cf914f}
  .name{font-weight:700} .flag{font-size:18px;margin-right:9px}
  .gbadge{display:inline-block;font-size:11px;font-weight:800;color:var(--gold);
    background:color-mix(in oklab,var(--gold) 13%,transparent);
    border:1px solid color-mix(in oklab,var(--gold) 24%,transparent);
    border-radius:6px;padding:1px 7px;margin-left:8px;vertical-align:middle}
  .bar{position:relative;height:22px;background:var(--ink);border-radius:7px;overflow:hidden;min-width:120px}
  .bar > i{position:absolute;inset:0 auto 0 0;background:var(--gold);border-radius:7px}
  #tbody .bar > i{inset:0;clip-path:inset(0 100% 0 0 round 7px);
    transition:clip-path .3s var(--ease-out)}
  #tbody.noanim .bar > i{transition:none}
  .bar > span{position:absolute;right:8px;top:0;line-height:22px;font-size:12px;font-weight:800;
    color:var(--text);text-shadow:0 1px 2px #000a}
  .det td{padding:0}
  .detbox{padding:14px 18px;background:var(--ink);border-bottom:1px solid var(--line);
    display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:14px;align-items:center;
    animation:det-in .2s var(--ease-out)}
  @keyframes det-in{from{opacity:0;transform:translateY(-4px)}}
  .detbox .kv b{display:block;font-size:16px} .detbox .kv span{color:var(--muted);font-size:12px}
  .detbox .joke{grid-column:1/-1;font-style:italic;color:#e7dcc6;
    background:color-mix(in oklab,var(--gold) 8%,transparent);border-radius:8px;padding:10px 14px}
  footer{margin-top:88px;color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:34px}
  .closer{font-family:var(--serif);font-size:clamp(22px,3.4vw,34px);line-height:1.3;
    color:var(--text);margin:0 0 22px;max-width:26ch}
  .closer i{color:var(--gold);font-style:normal}
  .groups{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:14px}
  .grp{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
  .grp h4{margin:0 0 6px;font-size:13px;color:var(--gold);font-family:var(--serif)} .grp div{font-size:13px;padding:1px 0}
  h2.sec{font-size:clamp(22px,3vw,26px);margin:76px 0 10px;padding-top:34px;
    border-top:1px solid #ffffff0d;scroll-margin-top:84px}
  .fxg{margin:16px 0 4px;color:var(--gold);font-weight:800;font-size:14px}
  .fx{display:grid;grid-template-columns:1fr 168px 46px 1fr;gap:10px;align-items:center;
    padding:7px 0;border-bottom:1px solid #1a2440;font-size:14px;cursor:pointer;
    transition:background .15s ease}
  @media(hover:hover) and (pointer:fine){
    .fx:hover{background:#172238aa}
  }
  .fxdet{padding:8px 0 12px;max-width:420px;margin:0 auto;animation:det-in .18s var(--ease-out)}
  .fxd{display:grid;grid-template-columns:42px 1fr 44px;gap:8px;align-items:center;padding:2px 0;font-size:13px}
  .fxd .bar{height:12px;background:#0c1426;border-radius:4px;overflow:hidden}
  .fxd .bar i{display:block;height:100%;background:var(--gold)}
  .fx .h{text-align:right;font-weight:600} .fx .a{text-align:left;font-weight:600}
  .fxbar{height:16px;border-radius:5px;overflow:hidden;display:flex;background:#0c1426}
  .fxbar i{height:100%}
  .fxpct{font-size:11px;color:var(--muted);text-align:center;margin-top:2px;font-variant-numeric:tabular-nums}
  .fxs{text-align:center;font-weight:800;background:#172238;border:1px solid var(--line);
    border-radius:6px;padding:3px 0;font-variant-numeric:tabular-nums}
  @media(max-width:640px){.fx{grid-template-columns:1fr 84px 1fr}.fx .fxs{display:none}}
  @media(prefers-reduced-motion:reduce){
    html{scroll-behavior:auto}
    .stat,.detbox,.fxdet{animation-duration:.01ms}
    #oracle-text{animation:none}
    .ticker-track{animation:none}
    .io,.io.in{opacity:1;transform:none;transition:none}
    #tbody .bar > i,.oracle button,.seg button{transition:none}
    @media(hover:hover) and (pointer:fine){.oracle button:hover{transform:none}}
  }
</style>
</head>
<body>
<nav class="pill" aria-label="Sektionen">
  <a href="#rangliste">Rangliste</a>
  <a href="#rennen">Titelrennen</a>
  <a href="#spielplan">Spielplan</a>
  <a href="#gruppen">Gruppen</a>
</nav>
<div class="wrap">

  <header class="hero">
    <span class="kicker">WM 2026 · USA · Mexiko · Kanada</span>
    <h1>Das Klement-Orakel</h1>
    <p class="sub">48 Nationen, 20.000 simulierte Turniere, ein Ökonom, der schwört, dass
      so etwas nicht funktioniert — und dreimal in Folge den Weltmeister traf. Wir glauben
      ihm. Irgendwie.</p>
    <div class="stats" id="stats"></div>
    <div class="ticker" aria-hidden="true"><div class="ticker-track" id="ticker"></div></div>
  </header>

  <div class="cards">
    <div class="card tip">
      <div class="k">Klements Tipp</div>
      <div class="big">🇳🇱 Niederlande</div>
      <div class="muted">Das Modell sagt: <b id="nl-p"></b> Titelchance. Klement sagt:
        „vertrau mir". Die stärkste Nation, die nie Weltmeister wurde — bei Holländern
        fast schon Tradition.</div>
    </div>
    <div class="card brk">
      <div class="k">Kuriosität aus dem Turnierbaum</div>
      <div class="big">🇩🇪 Deutschland – 🇫🇷 Frankreich</div>
      <div class="muted">Treffen laut offiziellem FIFA-Baum schon im <b>Achtelfinale</b>
        aufeinander (Sieger Gruppe E gegen Sieger Gruppe I) — genau wie im SPIEGEL-Interview.
        Für eines der beiden ist dann früh Badehosen-Zeit.</div>
    </div>
  </div>

  <div class="oracle">
    <button onclick="askOracle()">Frag das Orakel</button>
    <div id="oracle-text"><b>Tipp:</b> Drück den Knopf. Das Orakel hat Meinungen.</div>
  </div>

  <h2 class="sec" id="rangliste">Rangliste aller 48 Nationen</h2>
  <p class="muted" style="margin:-2px 0 10px"><b style="color:var(--gold)">/*STAND*/</b></p>
  <p id="eliminated" class="muted" style="margin:-4px 0 12px;font-size:13px"></p>
  <div class="controls">
    <input id="search" type="search" placeholder="Team suchen…" oninput="render()">
    <select id="grp" onchange="render()"></select>
    <div class="seg" id="metric">
      <button data-m="titel" class="on">Titel</button>
      <button data-m="finale">Finale</button>
      <button data-m="halb">Halbfinale</button>
      <button data-m="achtel">Achtelfinale</button>
    </div>
  </div>
  <table>
    <thead><tr>
      <th class="r" data-s="rank">#</th>
      <th data-s="team">Nation</th>
      <th data-s="metric">Wahrscheinlichkeit ▾</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>

  <h2 class="sec">Modell vs. Mensch</h2>
  <p class="muted" style="max-width:720px">ESPNs Experten-Panel (20 Reporter) gewichtet weiche
    Faktoren, die unser Modell strukturell nicht kennt: Verletzungen, aktuelle Form, Trainer,
    Momentum. Wo beide übereinstimmen, ist die Prognose robust — wo sie auseinandergehen
    (großes Δ), sitzt der blinde Fleck. ESPNs eigenes Kader-Modell (Elo + Marktwert) ist
    quasi unser Zwilling.</p>
  <table>
    <thead><tr><th>Team</th><th class="r">Modell</th><th class="r">Experten</th>
      <th class="r">ESPN-Kader</th><th class="r">Δ</th><th>Kommentar</th></tr></thead>
    <tbody id="espn"></tbody>
  </table>

  <h2 class="sec">Mythos-Check: die „Turniermannschaft"</h2>
  <p class="muted" style="max-width:720px">Gibt es Teams, die bei Turnieren über sich
    hinauswachsen? Wir haben je Team einen „Turnier-Bonus" geschätzt — und ihn dann
    ehrlich <b>nach vorn</b> getestet (auf einer WM, die das Modell nicht kannte).</p>
  <div class="cards" id="myth"></div>

  <h2 class="sec">Aschenputtel — das Modell weiß nicht WER, aber DASS</h2>
  <p class="muted" style="max-width:720px" id="cind-intro"></p>
  <div class="cards" id="cinderella"></div>

  <h2 class="sec" id="dritte">Tabelle der besten Dritten</h2>
  <p class="muted" style="max-width:720px">Im 48er-Format ziehen neben den 24 Gruppen-Ersten
    und -Zweiten die <b>8 besten Gruppendritten</b> ins Sechzehntelfinale ein. Hier der
    Zwischenstand (provisorisch, Gruppen haben teils unterschiedlich viele Spiele): links
    der aktuelle Dritte je Gruppe nach FIFA-2026-Kriterien, rechts die Modell-Chance, am
    Ende tatsächlich einer der 8 zu sein.</p>
  <div id="thirds"></div>

  <h2 class="sec" id="rennen">Titelrennen über die Zeit</h2>
  <p class="muted" style="max-width:720px">Titelchance je Snapshot (täglich nach den
    Spielen: frisches Elo, fixierte Ergebnisse, eingefrorene Kalibrierung). Wer bricht
    aus, wer bricht ein?</p>
  /*RACE*/

  <h2 class="sec" id="spielplan">Spielplan & Prognosen</h2>
  <p class="muted" style="max-width:720px">Jedes der 72 Gruppenspiele mit der
    Outcome-Wahrscheinlichkeit <b style="color:var(--green)">Heimsieg</b> /
    <b style="color:#8a98bf">Remis</b> / <b style="color:var(--blue)">Auswärtssieg</b>
    und dem wahrscheinlichsten Ergebnis.</p>
  <div id="fixtures"></div>

  <h2 class="sec" id="gruppen">Die 12 Gruppen</h2>
  <div class="groups" id="groups"></div>

  <footer>
    <p class="closer">„Wer aufgrund dieser Prognose Geld setzt, <i>dem ist nicht zu
      helfen.</i>"</p>
    <b>Modell:</b> Angriff/Abwehr-Poisson mit Dixon-Coles, kalibriert auf ~1.000 echten
    Länderspielen (Out-of-sample-Log-Loss 0,985 < Basisrate 1,085), offizieller FIFA-K.-o.-Baum,
    Heimvorteil der Gastgeber. Stärke ≈ Marktwert + Elo (Angriff) / Elo + FIFA-Ranking (Abwehr).
    <b>/*STAND*/</b>, inkl. bekannter Ausfälle/Sperren (vom Kaderwert abgezogen) und
    fixierter Live-Ergebnisse.<br><br>
    <b>Disclaimer im Geiste Klements:</b> Selbst der Favorit gewinnt nur ~1 von 6 Turnieren.
    Das Zitat oben stammt von ihm. Es ist ein Zitat. Kein Tipp.
  </footer>
</div>

<script>
const D = /*DATA*/;
const METRIC = {titel:"Titel", finale:"Finale", halb:"Halbfinale", achtel:"Achtelfinale"};
let metric = "titel", sortKey = "metric", asc = false;

const pct = x => (x*100).toFixed(1).replace(".",",")+" %";
const nice = x => x.toLocaleString("de-DE");

// Stat-Kacheln
const fav = D.favorit;
document.getElementById("stats").innerHTML = [
  ["🥇 Favorit", fav.flag+" "+fav.team, pct(fav.titel)+" Titelchance"],
  ["🎲 Realismus", "5 von 6", "Turnieren gewinnt NICHT der Favorit"],
  ["💶 Gesamtmarktwert", "17,49 Mrd. €", "aller 48 Kader (Transfermarkt)"],
  ["🧮 Simulationen", "20.000", "Monte-Carlo-Turniere"],
].map(s=>`<div class="stat"><b>${s[1]}</b><span>${s[0]} — ${s[2]}</span></div>`).join("");
document.getElementById("nl-p").textContent =
  pct((D.rows.find(r=>r.key==="Niederlande")||{titel:0}).titel);

// Gruppen-Filter
const gsel = document.getElementById("grp");
gsel.innerHTML = '<option value="">Alle Gruppen</option>' +
  Object.keys(D.groups).sort().map(g=>`<option value="${g}">Gruppe ${g}</option>`).join("");

// Gruppen-Karten
document.getElementById("groups").innerHTML = Object.keys(D.groups).sort().map(g=>
  `<div class="grp"><h4>Gruppe ${g}</h4>${D.groups[g].map(t=>{
     const r=D.rows.find(x=>x.team===t)||{flag:"🏳️"};
     return `<div${r.dead?' style="opacity:.5"':''}>${r.flag} ${t}${r.dead?' 💀':''}</div>`;
   }).join("")}</div>`).join("");

// Kompakte "Ausgeschieden"-Zeile unter der Rangliste (sofort sichtbar)
(function(){
  const dead=D.rows.filter(r=>r.dead);
  const el=document.getElementById("eliminated"); if(!el) return;
  el.innerHTML = dead.length
    ? `💀 <b>Ausgeschieden:</b> ${dead.map(r=>r.flag+" "+r.team).join(" · ")}`
    : "";
})();

// Spielplan & Prognosen
(function(){
  const fx=D.fixtures; if(!fx) return;
  const byg={}; fx.forEach(f=>(byg[f.group]=byg[f.group]||[]).push(f));
  let html="";
  let n=0;
  Object.keys(byg).sort().forEach(g=>{
    html+=`<div class="fxg">Gruppe ${g}</div>`;
    byg[g].forEach(f=>{
      const id="fxd"+(n++);
      const ph=Math.round(f.ph*100), pd=Math.round(f.pd*100), pa=Math.round(f.pa*100);
      const mx=Math.max(...f.dist.map(d=>d[2]));
      const dist=f.dist.map(d=>`<div class="fxd"><span class="tnum">${d[0]}:${d[1]}</span>
        <span class="bar"><i style="width:${d[2]/mx*100}%"></i></span>
        <span class="tnum muted">${(d[2]*100).toFixed(0)} %</span></div>`).join("");
      html+=`<div class="fx" onclick="tgl('${id}')">
        <span class="h">${f.hn} <span class="flag">${f.hf}</span></span>
        <div><div class="fxbar">
          <i style="width:${f.ph*100}%;background:var(--green)"></i>
          <i style="width:${f.pd*100}%;background:#5c6c95"></i>
          <i style="width:${f.pa*100}%;background:var(--blue)"></i></div>
          <div class="fxpct">${ph} / ${pd} / ${pa}</div></div>
        <span class="fxs">${f.score[0]}:${f.score[1]}</span>
        <span class="a"><span class="flag">${f.af}</span> ${f.an}</span></div>
        <div class="fxdet" id="${id}" style="display:none">
          <div class="fxpct" style="margin-bottom:4px">wahrscheinlichste Ergebnisse</div>${dist}</div>`;
    });
  });
  document.getElementById("fixtures").innerHTML=html;
  window.tgl=id=>{const e=document.getElementById(id);e.style.display=e.style.display==="none"?"block":"none";};
})();

// Aschenputtel — Dark Horses 2026 + historischer Tail-Check
(function(){
  document.getElementById("cind-intro").innerHTML=
    `In einem typischen simulierten Turnier sitzen <b>~${(D.exp_out_sf||0).toString().replace(".",",")} von 4</b>
     Halbfinalisten außerhalb der Top-8 — fast immer überrascht <i>irgendwer</i>. Welcher? Unklar.
     Aber das Modell schließt es nie aus (kleine, echte Chancen):`;
  const dh=(D.darkhorses||[]).map(x=>`<div style="display:flex;justify-content:space-between;padding:3px 0">
     <span><span class="flag">${x.flag}</span>${x.name}</span>
     <span class="tnum muted">Titel ${pct(x.titel)} · <b style="color:var(--text)">VF ${(x.achtel*100).toFixed(0)} %</b></span></div>`).join("");
  const cind=(D.cinderella||[]).map(c=>`<div style="display:flex;justify-content:space-between;padding:3px 0">
     <span><span class="flag">${c.flag}</span>${c.name} <span class="muted">'${c.year.slice(2)} (${c.reached})</span></span>
     <b class="tnum" style="color:#f3c14a">${pct(c.p_run)}</b></div>`).join("");
  document.getElementById("cinderella").innerHTML=`
    <div class="card brk">
      <div class="k">Dark Horses 2026</div>
      <div style="margin:8px 0 4px;font-size:13px;color:var(--muted)">kleine Titelchance, aber reale Tiefenläufer-Quote</div>
      ${dh}
    </div>
    <div class="card tip">
      <div class="k">🕰️ Hätte das Modell die echten Sensationen vorab für möglich gehalten?</div>
      <div style="margin:8px 0 4px;font-size:13px;color:var(--muted)">pre-Turnier-Chance ihres tatsächlichen K.-o.-Laufs</div>
      ${cind}
      <div class="muted" style="margin-top:10px;font-style:italic">Klein, aber nie 0. Ein „Chalk"-Modell gäbe Marokko &lt;0,5 % — überheblich.</div>
    </div>`;
})();

// Tabelle der besten Dritten
(function(){
  const t3=D.thirds||[]; const el=document.getElementById("thirds"); if(!el) return;
  if(!t3.length){el.innerHTML='<p class="muted">Erscheint im Live-Betrieb (sobald Spiele gespielt sind).</p>';return;}
  let rows="";
  t3.forEach((d,i)=>{
    const cls=(d.qualified?"q":"")+(i===7?" cut":"");
    rows+=`<tr class="${cls}">
      <td>${i+1}</td>
      <td><span class="gtag">${d.group}</span> <span class="flag">${d.flag}</span>${d.name}</td>
      <td>${d.pl}</td><td>${d.pts}</td>
      <td>${d.gd>0?"+":""}${d.gd}</td>
      <td><span class="qbar"><i style="width:${Math.round(d.p_qualify*100)}%"></i></span>${pct(d.p_qualify)}</td>
      <td>${d.qualified?'<span style="color:var(--green)">✓ drin</span>':'<span class="muted">raus</span>'}</td>
    </tr>`;
  });
  el.innerHTML=`<table><thead><tr>
    <th>#</th><th>Gruppe · Team</th><th>Sp</th><th>Pkt</th><th>Diff</th>
    <th>P(am Ende dabei)</th><th>Stand</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="muted" style="font-size:12px;margin-top:8px">Goldene Linie = Qualifikationsgrenze (Top 8).
    Achtung: provisorisch, Gruppen mit weniger Spielen können noch klettern (siehe P-Spalte).</p>`;
})();

// Mythos-Check: "Turniermannschaft"
(function(){
  const m=D.myth; if(!m) return;
  const row=(x,cls)=>`<div style="display:flex;justify-content:space-between;padding:3px 0">
     <span><span class="flag">${x.flag}</span>${x.name}</span>
     <b class="tnum" style="${cls}">${x.beta>0?"+":""}${x.beta}</b></div>`;
  const better=m.better;
  const loo=m.loo.map(r=>`<div style="display:flex;justify-content:space-between;padding:3px 0">
     <span class="muted">WM ${r.year}</span>
     <span class="tnum">${r.base.toFixed(3)} → <b style="color:${r.bonus<r.base?'#57b88a':'#e07f8b'}">${r.bonus.toFixed(3)}</b></span></div>`).join("");
  document.getElementById("myth").innerHTML=`
    <div class="card tip">
      <div class="k">😍 So überzeugend sieht es rückblickend aus</div>
      <div style="margin:10px 0 4px;font-size:13px;color:var(--muted)">„Turnier-Bonus" (Elo-Punkte), geschätzt aus 2014/18/22</div>
      <div style="color:#bfe9d2">${m.overperformers.map(x=>row(x,"color:#57b88a")).join("")}</div>
      <div style="border-top:1px solid var(--line);margin:8px 0"></div>
      <div style="color:#f3c9cf">${m.underperformers.map(x=>row(x,"color:#e07f8b")).join("")}</div>
      <div class="muted" style="margin-top:10px;font-style:italic">Frankreich liefert, Brasilien „chokt" — jeder Stammtisch nickt.</div>
    </div>
    <div class="card brk">
      <div class="k">🧪 Und dann der Test nach vorn</div>
      <div style="margin:10px 0">${loo}</div>
      <div style="border-top:1px solid var(--line);margin:8px 0"></div>
      <div style="display:flex;justify-content:space-between;font-size:17px">
        <b>Gesamt</b><span class="tnum">${m.overall_base.toFixed(3)} →
        <b style="color:${better?'#57b88a':'#e07f8b'}">${m.overall_bonus.toFixed(3)}</b></span></div>
      <div class="big" style="color:${better?'#57b88a':'#e07f8b'};margin-top:10px">
        ${better?"hilft":"macht es schlechter"}</div>
      <div class="muted">Der Bonus verschlechtert die Vorhersage auf der ausgelassenen WM.
        Die Liste links ist Hindsight-Rauschen — <b>kein</b> echtes Muster. Genau Klements These.</div>
    </div>`;
})();

// Modell vs. Experten
(function(){
  const meta={}; D.rows.forEach((r,i)=>meta[r.key]={rank:i+1,flag:r.flag,team:r.team});
  const keys=[...new Set([...Object.keys(D.espn_expert),...Object.keys(D.espn_squad)])]
    .sort((a,b)=>(D.espn_expert[a]||99)-(D.espn_expert[b]||99));
  document.getElementById("espn").innerHTML=keys.map(k=>{
    const m=meta[k]||{rank:"–",flag:"🏳️",team:k};
    const e=D.espn_expert[k], s=D.espn_squad[k];
    const d=(e&&typeof m.rank==="number")?m.rank-e:null;
    const col=d===null?"":Math.abs(d)>=3?"color:#e07f8b;font-weight:800":Math.abs(d)<=1?"color:#57b88a":"color:#f3c14a";
    const dtxt=d===null?"–":(d>0?"+"+d:d);
    return `<tr><td class="name"><span class="flag">${m.flag}</span>${m.team}</td>
      <td class="r tnum">${m.rank}</td><td class="r tnum">${e||"–"}</td>
      <td class="r tnum">${s||"–"}</td><td class="r tnum" style="${col}">${dtxt}</td>
      <td class="muted" style="font-size:13px">${D.espn_notes[k]||""}</td></tr>`;
  }).join("");
})();

// Metrik-Umschalter
document.querySelectorAll("#metric button").forEach(b=>b.onclick=()=>{
  metric=b.dataset.m;
  document.querySelectorAll("#metric button").forEach(x=>x.classList.toggle("on",x===b));
  if(sortKey==="metric") asc=false;
  animateBars=true;       // Metrik-Wechsel = neue Daten -> Balken duerfen einmal einschwingen
  render();
});
// Sortierung per Spaltenkopf
document.querySelectorAll("thead th").forEach(th=>th.onclick=()=>{
  const k=th.dataset.s; if(sortKey===k){asc=!asc}else{sortKey=k;asc=(k==="team")}
  render();
});

let openKey = null;
let animateBars = true;   // nur Erstladung + Metrik-Wechsel animieren; Suche/Sortieren/Aufklappen nicht
function render(){
  const q=(document.getElementById("search").value||"").toLowerCase();
  const gf=gsel.value;
  let rows=D.rows.filter(r=>r.team.toLowerCase().includes(q) && (!gf||r.group===gf));
  const val=r=>sortKey==="team"?r.team:sortKey==="rank"?-r.titel:r[metric];
  rows.sort((a,b)=>{const x=val(a),y=val(b);
    if(typeof x==="string")return asc?x.localeCompare(y):y.localeCompare(x);
    return asc?x-y:y-x;});
  const max=Math.max(...D.rows.map(r=>r[metric]),0.0001);
  document.querySelector('th[data-s="metric"]').textContent =
    "Wahrscheinlichkeit · "+METRIC[metric]+(sortKey==="metric"?(asc?" ▴":" ▾"):"");

  const tb=document.getElementById("tbody"); tb.innerHTML="";
  tb.classList.toggle("noanim",!animateBars);
  rows.forEach((r,i)=>{
    const overall=D.rows.indexOf(r)+1;
    const tr=document.createElement("tr");
    tr.className="main"+(overall<=3?" top"+overall:"")+(r.dead?" dead":"");
    tr.innerHTML=`<td class="r rank">${overall}</td>
      <td class="name"><span class="flag">${r.flag}</span>${r.dead?'<span class="skull" title="Offiziell ausgeschieden">💀</span>':""}${r.team}
        <span class="gbadge">${r.group}</span></td>
      <td><div class="bar"><i></i><span>${pct(r[metric])}</span></div></td>`;
    tr.onclick=()=>toggle(r.key);
    tb.appendChild(tr);
    const cp=`inset(0 ${100-r[metric]/max*100}% 0 0 round 7px)`;
    const fill=tr.querySelector(".bar > i");
    if(animateBars){requestAnimationFrame(()=>requestAnimationFrame(()=>fill.style.clipPath=cp));}
    else{fill.style.clipPath=cp;}
    if(openKey===r.key){
      const d=document.createElement("tr"); d.className="det";
      const band=(r.lo||r.hi)?`<div class="kv"><b>${pct(r.lo)} – ${pct(r.hi)}</b><span>90%-Band (Titel)</span></div>`:"";
      d.innerHTML=`<td colspan="3"><div class="detbox">
        <div class="kv"><b>#${overall}</b><span>Gesamtrang</span></div>
        <div class="kv"><b>${pct(r.finale)}</b><span>Finale</span></div>
        <div class="kv"><b>${pct(r.halb)}</b><span>Halbfinale</span></div>
        <div class="kv"><b>${pct(r.achtel)}</b><span>Achtelfinale</span></div>
        <div class="kv"><b>${nice(r.marktwert)} Mio €</b><span>Kader-Marktwert</span></div>
        <div class="kv"><b>${nice(r.fifa)}</b><span>FIFA-Punkte</span></div>
        <div class="kv"><b>${nice(r.elo)}</b><span>Elo-Rating</span></div>
        ${band}
        ${r.inj&&r.inj.length?`<div class="joke" style="border-color:var(--red)"><b>Ausfälle:</b> ${r.inj.join(", ")} <span class="muted">(* fraglich)</span></div>`:""}
        ${r.joke?`<div class="joke">${r.joke}</div>`:""}
      </div></td>`;
      tb.appendChild(d);
    }
  });
  animateBars=false;   // verbraucht: naechster render (Suche/Sort/Toggle) ohne Replay
}
function toggle(k){openKey=openKey===k?null:k;render();}

let lastOracle=-1;
function askOracle(){
  let i; do{i=Math.floor(Math.random()*D.oracle.length)}while(i===lastOracle&&D.oracle.length>1);
  lastOracle=i;
  const el=document.getElementById("oracle-text");
  el.style.animation="none"; void el.offsetWidth;   // Animation neu triggern
  el.style.animation="";
  el.innerHTML="<b>Orakel:</b> "+D.oracle[i];
}
render();

// Titelchancen-Ticker (Marquee): Inhalt doppelt fuer nahtlosen Loop
(function(){
  const t=document.getElementById("ticker"); if(!t) return;
  const top=[...D.rows].sort((a,b)=>b.titel-a.titel).slice(0,16);
  const items=top.map(r=>`<span>${r.flag} ${r.team} <b>${pct(r.titel)}</b></span>`).join("");
  t.innerHTML=items+items;
})();

// Scroll-Reveals (nur Ueberschriften + Closer; Daten bleiben sofort sichtbar)
(function(){
  if(matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const els=document.querySelectorAll("h2.sec,.closer");
  els.forEach(e=>e.classList.add("io"));
  const ob=new IntersectionObserver(es=>es.forEach(x=>{
    if(x.isIntersecting){x.target.classList.add("in");ob.unobserve(x.target);}
  }),{rootMargin:"0px 0px -60px 0px"});
  els.forEach(e=>ob.observe(e));
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
