# WM-2026-Prognosemodell (nach Klement)

Rekonstruktion des Prognosemodells von Ökonom Joachim Klement (SPIEGEL, 03.06.2026):
wenige Länder-Variablen → Stärke-Score → Monte-Carlo über den echten Turnierbaum.
Konzept und Begründung: [MODELLPLANUNG.md](MODELLPLANUNG.md).

> ⚠️ **Variablenwerte sind illustrativ/grob recherchiert.** Die Modell­parameter
> (Gewichte, Steilheit) sind jedoch **per Poisson-Regression auf 1008 echten
> Länderspielen kalibriert** und schlagen out-of-sample die Basisrate.
> Im Geist Klements: „Wer darauf Geld setzt, dem ist nicht zu helfen."

## Schnellstart

Reine Python-Standardbibliothek — keine Installation nötig (Python 3.9+).

```bash
python3 src/calibrate.py    # Poisson-Regression auf echten Spielen -> calibrated_params.json
python3 src/model.py        # volle 2026-Simulation, 48 Teams (nutzt Kalibrierung autom.)
python3 src/validate.py     # Reliabilitätsdiagramm + Backtest gegen WM 2014/18/22
python3 src/uncertainty.py  # Bootstrap: 90%-Unsicherheitsband je Titel-Wahrscheinlichkeit
python3 src/calib_check.py  # Torraten-Check (Momentenabgleich)
python3 src/simulate_report.py 1000   # 1000 Turniere: Gruppenphase-Quoten + Titel
python3 src/match_predictions.py      # je Gruppenspiel: W/D/L + wahrscheinlichstes Ergebnis
python3 src/playthrough.py [seed]     # EIN komplettes Turnier mit Ergebnissen ausspielen
python3 src/injuries.py               # Wirkung der bekannten Ausfälle auf die Prognose
python3 src/snapshot.py               # Live-Snapshot: Ergebnisse fixieren, Rest simulieren, Diff
python3 src/dashboard.py    # baut output/dashboard.html (interaktiv, offline)
python3 src/prototype.py    # Mini-Durchstich (8 Teams) zum Nachvollziehen
```

Das **Dashboard** (`output/dashboard.html`) einfach im Browser öffnen: sortier-/filterbare
Rangliste aller 48 Nationen, Metrik-Umschalter (Titel/Finale/Halbfinale/Achtelfinale),
einen **Spielplan** mit Outcome-Prognose und wahrscheinlichstem Ergebnis je Gruppenspiel,
aufklappbare Team-Details (inkl. Elo + Unsicherheitsband), eine **„Modell vs. Mensch"**-
Sektion (Divergenz zu ESPNs Experten-Panel), einen **„Mythos-Check"** (die
„Turniermannschaft" — verführerisch in-sample, wertlos out-of-sample), eine
**„Aschenputtel"**-Sektion (Dark Horses 2026 + Tail-Check: welche reale Chance hätte
das Modell echten Sensationen vorab gegeben) — und ein „Orakel" für den Schmunzler.

Ohne `calibrated_params.json` läuft `model.py` im Fallback-Modus „heuristisch".
`calibrate.py` braucht `data/raw/results.csv` (martj42/international_results).

## Struktur

```
modell/
├── MODELLPLANUNG.md            # Konzept, Variablen, Roadmap, Risiken
├── README.md
├── data/
│   ├── teams_2026.csv          # 48 Teams × 4 Variablen (illustrativ)
│   ├── groups_2026.json        # Gruppenauslosung A–L (05.12.2025)
│   ├── calibrated_params.json  # gefittete Parameter (erzeugt von calibrate.py)
│   ├── raw/results.csv         # historische Länderspiele (für Kalibrierung)
│   └── teams.csv               # Prototyp-Datensatz (8 Teams)
├── src/
│   ├── model.py                # vollständiges 2026-Modell (Hauptdatei, echter FIFA-Baum)
│   ├── calibrate.py            # Poisson-Regression: fittet Gewichte + Steilheit
│   ├── validate.py             # Reliabilität (ECE) + historischer Elo-Backtest
│   ├── uncertainty.py          # Bootstrap-Unsicherheitsbänder (Parameter)
│   ├── rating.py               # Team-Rating + Klement-Prior (Experiment, s.u.)
│   ├── calib_check.py          # Torraten-Momentenabgleich
│   └── prototype.py            # Mini-Prototyp
└── output/
    └── win_probabilities_2026.csv   # erzeugte Wahrscheinlichkeiten je Team
```

## Modell in einem Satz

Fünf Variablen (Wohlstand, Bevölkerung, Marktwert, FIFA-Punkte, **Elo-Rating**)
→ kalibrierte **Angriff/Abwehr-Stärke** je Team → **Dixon-Coles-Poisson**
je Spiel (λ_i = MU·exp(att_i − def_j) + Heimvorteil) → Gruppenphase (12×4, beste 8
Dritte, FIFA-Tiebreaker) → offizieller K.-o.-Baum → 20.000 Monte-Carlo-Läufe.
Bekannte **Ausfälle** (`data/injuries_2026.json`) werden vom Kader-Marktwert abgezogen
(„out" voll, „doubtful" 50 %); Elo bleibt unverändert.

**Live-Snapshots während des Turniers** (`src/snapshot.py`, Cron täglich 23:45 + 09:30
im Juni/Juli): lädt frische Ergebnisse, fixiert gespielte Spiele (Conditioning),
aktualisiert Elo, simuliert den Rest und schreibt `output/snapshots/` + `history.csv`.
Diff zum Vortag markiert große Sprünge als „⚡AUSBRUCH". Zusätzlich **Live-Eval**: das
eingefrorene Vorturnier-Modell wird an jedem gespielten Spiel gemessen (LogLoss vs.
Basisrate) — die WM als unberührtes Test-Set. Idempotent: ohne neue Spiele kein neuer
Snapshot. Cron entfernen: `crontab -e` (Zeilen mit `snapshot.py`).

**Nach jeder Datenänderung:** `./run_all.sh` (erzwingt die Pipeline-Reihenfolge).
Das Dashboard zeigt ab dem 2. Snapshot das **Titelrennen über die Zeit** (SVG-Chart).

### Cloud-Automation

`.github/workflows/snapshot.yml` baut und deployed das Dashboard per GitHub Actions
täglich um **09:30 Europe/Berlin** (`07:30 UTC`, Juni/Juli) und zusätzlich um 16:00.
Der Ablauf ist:

```bash
python3 src/update_availability.py  # optionaler JSON-Feed, sonst Validierung
python3 src/update_cards_public.py --apply-safe  # rote Karten aus oeffentlichen Quellen
python3 src/update_cards.py         # optionaler Paid/API-Fallback, sonst Validierung
python3 src/snapshot.py             # Ergebnisse laden, Elo live, Rest simulieren
python3 src/incentives.py           # Spielzustand: Sieg/Remis/Niederlage-Szenarien
python3 src/context_factors.py      # Belastung/Reise/Klima-Kontext
python3 src/explain_snapshot.py     # taegliche Delta-Erklaerung
python3 src/dashboard.py            # output/dashboard.html
```

Die kostenlose Kartenstufe schreibt alle Funde nach `data/raw/cards_public_candidates.json`
und merged nur sichere rote Karten/Sperren in `data/cards_2026.json`. Gelbe Karten
werden nicht blind aus News/Wikipedia erzeugt, weil fuer den Fair-Play-Tiebreaker eine
unvollstaendige Gelb-Liste schlechter ist als eine ehrliche manuelle/amtliche Quelle.

Optionale GitHub-Einstellungen fuer Zusatzquellen:

| Name | Typ | Zweck |
|------|-----|-------|
| `API_FOOTBALL_KEY` | Secret | optional: Karten-Events aus API-Football statt nur Public Sources |
| `API_FOOTBALL_LEAGUE_ID` | Variable | API-Football League-ID, Default `1` |
| `API_FOOTBALL_SEASON` | Variable | Saison, Default `2026` |
| `AVAILABILITY_JSON_URL` | Secret | Kuratierter Ausfall-/Availability-Feed im Format von `injuries_2026.json` |

Ohne diese Secrets läuft die Pipeline weiter und validiert nur die bestehenden Dateien.
Auch Feed-Fehler blockieren den Snapshot nicht; der letzte bekannte Datenstand bleibt
aktiv. Der Zustand der Datenstufen landet in `output/automation_status.json` und wird
im Dashboard unter dem Live-Stand angezeigt.
Die taegliche Kurz-Erklaerung landet in `output/snapshot_explain.json` und beantwortet
im Dashboard automatisch, welche Teams sich im letzten Snapshot am staerksten bewegt
haben und warum (Live-Elo, Ausscheiden, Gruppenweg, Bracket/Restfeld).
Der Spielzustand landet in `output/match_incentives.json`: fuer offene Gruppenspiele
simuliert er Weiterkommens-Chancen unter Sieg/Remis/Niederlage und markiert daraus
Labels wie “muss gewinnen”, “Remis reicht fast sicher” oder “sicher weiter”.
Belastung/Reise/Klima landen in `output/context_factors.json` als Dashboard-Kontext.
Das ist bewusst kein kalibriertes Feature, sondern ein Hinweis-Layer fuer Resttage,
lange Reisen, Hitze/Feuchte/Hoehe und moegliche Rotation.

`data/injuries_2026.json` kann neben `out`/`doubtful` auch feinere Availability-Status
nutzen: `limited`/`knock` (35 % Wertabzug), `rested`/`rotation`/`bench` (25 %),
`fit`/`available` (0 %) oder explizit `factor`. Sperren in `data/cards_2026.json`
koennen optional `role`/`position` tragen (`gk`, `def`, `dm`, `mid`, `wing`, `st` usw.);
dann verteilt das Modell den Marktwert-Malus staerker auf Abwehr oder Angriff statt
pauschal auf beide Seiten.

**K.-o.-Detailmodell** (`src/test_ko_model.py`): Verlängerungs-Term und steilere
Elfmeter-Logistik wurden auf 144 historischen WM-K.-o.-Spielen getestet — beide
out-of-sample verworfen (Elfmeterschießen ist fast Münzwurf: Favorit gewann 17/31).

## Stellschrauben (oben in `src/model.py`)

| Parameter | Bedeutung |
|-----------|-----------|
| `WEIGHTS`, `BETA`, `MU` | Heuristik-Fallback (nur ohne `calibrated_params.json`) |
| `HOST_BONUS` | Heimvorteil: `None` = gefitteten Wert nutzen, Zahl = fest, 0 = aus |
| `N_SIMS`  | Anzahl Monte-Carlo-Läufe |

Im kalibrierten Modus kommen Gewichte und Steilheit aus `calibrated_params.json`.

## Befund der Kalibrierung

**Marktwert** treibt v. a. den **Angriff**, das **Elo-Rating** v. a. die **Abwehr**
(def[elo]≈0.20) — und verdrängt dabei die FIFA-Punkte fast vollständig (att/def ≈0.03),
weil Elo das bessere ergebnisbasierte Signal ist. BIP und Bevölkerung ≈ 0 %.
Das Elo wird lokal aus der Spielhistorie berechnet (eloratings.net-Methode).

## Validierungsstand

- Out-of-sample (ab 2025): Ergebnis-Log-Loss **0.9850** vs. Basis 1.085.
  Stufen: geschätzte Marktwerte 1.016 → echte Marktwerte 1.003 → att/def+Zeitgewicht+DC
  0.9998 → **+Elo-Variable 0.9850**.
- **Modellauswahl** (`calibrate.py`): vergleicht single / +Zeitgewicht / Angriff-Abwehr /
  Split+Zeitgewicht out-of-sample; gewinnt **att/def+decay**.
- **Dixon-Coles** (ρ=−0.06): hebt die Remisquote der Simulation ins Zielband (≈25 %).
- **Heimvorteil** der Gastgeber USA/Mexiko/Kanada: gefittete +0.15 log-Tore/Heimspiel.
- Reliabilität: **ECE 0.031**. Backtest WM 2014/18/22: schlägt **alle drei** Basisraten.
- **Champion-Backtest** (`validate.py`): echte Sieger lagen auf Rang 4/4/2; mittlere
  Ignoranz 3.05 bit vs. 5.0 uniform — besser als Zufall, aber Favoriten gewinnen oft nicht.
- K.-o.-Baum: **offizielles FIFA-Schema** (Spiele 73–104) inkl. Annex-C-Zuordnung.
- **Unsicherheitsbänder** (`uncertainty.py`): Parameter-Bootstrap → 90 %-Band je Titel.

## Experiment: Team-Rating + Klement-Prior (`rating.py`)

Getestet, ob ein aus Ergebnissen gelerntes Team-Rating (mit Klements Variablen als
Bayes-Prior) das Strukturmodell schlägt. **Ergebnis: nein** — out-of-sample 1.025 vs.
1.016; mit stärkerem Prior konvergiert das Rating monoton zurück zum Strukturmodell.
Marktwert + FIFA-Punkte sind hier kaum zu übertreffen. Das Skript übernimmt das
komplexere Modell daher **bewusst nicht** (Disziplin gegen Overfitting). Ein
ehrliches Negativergebnis — ganz im Geist von Klement.
