# CLAUDE.md — WM-2026-Prognosemodell (Klement-Rekonstruktion)

Kontext-Dokument für künftige Sessions. Stand: **2026-06-09, zwei Tage vor WM-Anpfiff**.

## Worum es geht

Rekonstruktion des WM-Prognosemodells von Ökonom **Joachim Klement** (SPIEGEL-Interview
03.06.2026). Klement traf 3× in Folge den Weltmeister (2014 DE, 2018 FR, 2022 AR),
hält sein eigenes Modell aber für „Lottospielen". 2026-Tipp Klement: **Niederlande**.
Wir haben sein Variablen-Modell nachgebaut, kalibriert, validiert und stark erweitert.

**Projektphilosophie (wichtigste Regel):** Jede Modelländerung muss sich am
**Out-of-sample-Harness beweisen** (Ergebnis-Log-Loss auf Spielen ab `TEST_FROM`),
sonst wird sie verworfen. Mehrere „plausible" Ideen sind genau daran gescheitert —
das ist gewollt und dokumentiert (Klements These: Disziplin gegen Overfitting).

## Modell in Kurzform

```
5 Variablen je Team (teams_2026.csv):
  bip_pc, bevoelkerung (≈0% Gewicht), marktwert (Transfermarkt, real),
  fifa_punkte (real), elo (lokal berechnet, eloratings.net-Methode)
→ log/z-Standardisierung (LOG_VARS: bip_pc, bevoelkerung, marktwert)
→ kalibrierte ANGRIFF/ABWEHR-Gewichte (Poisson-Regression, att/def+decay)
→ Tormodell: lambda_i = MU_EFF * exp(att_i − def_j [+ Heimvorteil USA/MEX/CAN])
→ Dixon-Coles-Korrektur (rho≈−0.055) für knappe Remis
→ Gruppenphase 12×4 (FIFA-Tiebreaker inkl. Direktvergleich) + beste 8 Dritte
→ offizieller FIFA-K.-o.-Baum (Spiele 73–104, Annex-C-Drittenzuordnung per Matching)
→ Monte-Carlo (20k Standard)
```

- **Befund:** Marktwert treibt den Angriff, Elo die Abwehr; Elo verdrängt FIFA-Punkte
  fast vollständig. BIP/Bevölkerung ≈ 0 %.
- **Ausfälle** (`data/injuries_2026.json`) werden in `build_scores()` vom Marktwert
  abgezogen („out" voll, „doubtful" 50 %). Elo bleibt unangetastet.
- **Karten & Sperren** (`data/cards_2026.json`, EINE Quelle, append-only): pro Team
  kumulierte Karten (yellow/yellow_red/red → `load_cards()` = FIFA-Fair-Play-Punkte,
  vorletztes Gruppen-Tiebreaker-Kriterium in `play_group`, nach Direktvergleich/vor Los)
  plus optional `bans[]`. Eine Sperre `{value, after}` (oder `{value, round}`) wird in
  `resolve_suspensions(played)` automatisch aufs nächste ungespielte Spiel gemappt,
  trifft NUR dieses (kein Weiterrollen) und verfällt selbst, sobald es gespielt ist
  (Live-Treiber reicht die gespielten Paarungen). `suspension_delta()` rechnet den
  Marktwert-Verlust über dieselbe Kalibrierung (log-MW-z × att/def-MW-Gewicht) in einen
  att/def-Malus, NUR fürs betroffene Match. Relativ zum Kaderwert (log) → Stars bewegen
  wenig (konsistent mit GOAT-Verwerfung). FAKTEN-Adjustierung wie Verletzungen, kein
  Vorhersage-Feature → kein Harness-Beweis, nur Korrektheit. **Claude pflegt die Datei
  je Spieltag** (Karten haben keinen Auto-Feed wie Ergebnisse); abgeleitete Schritte
  (welches Spiel, Fair-Play-Punkte, Verfall) macht der Code.
- Elfmeter/Verlängerung: fast Münzwurf, logistisch mit Steilheit `(scores-diff)/4`.

## Validierungs-Stand (alles erfüllt)

| Check | Ergebnis |
|---|---|
| Out-of-sample-Log-Loss (153 Spiele ab 2025) | **0.985** vs. Basisrate 1.085 |
| Entwicklung | 1.016 (geschätzte MW) → 1.003 (echte MW) → 0.9998 (att/def+decay+DC) → **0.985 (+Elo)** |
| Reliabilität (ECE) | 0.031–0.037, gut kalibriert |
| Elo-Backtest WM 2014/18/22 (Spielebene, kein Look-ahead) | schlägt Basisrate **3/3** |
| Historischer Sweep 1990–2022 (9 WMs, Elo) | Spielebene **9/9** besser als Basis; Favorit wird Weltmeister nur **1–2/9** |
| Torraten (calib_check) | 2.5–2.6 Tore/Spiel, Remis ~24–25 % (Zielband) |
| Bootstrap-Bänder | z. B. Spanien 16.1 % [14.2–18.0] |

**Aktuelle Prognose (inkl. Ausfälle):** Spanien ~16 % · Frankreich ~15 % ·
Argentinien ~12 % · England ~8 % · Portugal ~7 % · NL/DE ~5 % · Brasilien ~4 %.
Klements Niederlande: ~5 %. DE trifft lt. Baum im **Achtelfinale auf FR** (Sieger E vs I).

## Experimente: angenommen vs. verworfen

**Angenommen (Log-Loss sank):**
- Echte Transfermarkt-Marktwerte (User lieferte Screenshot)
- Angriff/Abwehr-Split + Zeitgewichtung (Halbwertszeit 3 J.)
- Dixon-Coles (rho per 1-D-MLE)
- Heimvorteil der Gastgeber (gefittet ~+0.15–0.16 log-Tore)
- **Elo als 5. Variable** (User-Idee; 0.9998→0.985 trotz r=0.90 zu FIFA-Punkten)

**Verworfen (Harness sagte nein) — NICHT wieder einführen ohne neuen Beweis:**
- `rating.py`: ergebnisbasiertes Team-Rating als ERSATZ der Strukturvariablen
  (konvergiert mit wachsendem Prior monoton zum Strukturmodell; 1.025 > 1.016)
- `test_age_feature.py`: Kader-Durchschnittsalter (0.9931→0.9942, redundant zu MW)
- `test_goat_feature.py`: GOAT/Star-Faktor, beide Varianten (topval 0.9967,
  topshare 0.9990) — Starpower steckt schon in MW+Elo
- `test_tournament_team.py`: „Turniermannschaft"-Bonus — in-sample perfekt narrativ
  (FR +113, BRA −109 Elo-Punkte), out-of-sample in **allen 3** Test-WMs schlechter.
  Bestes Lehrstück des Projekts (Hindsight-Rauschen).
- `test_altitude_feature.py`: Höhen-Heimbonus (+0.091 log-Tore nach Elo-Kontrolle,
  bestätigt auf nur 10 OOS-Spielen) — echtes Mini-Signal, aber NICHT eingebaut:
  beträfe nur Mexikos 2 Azteca-Spiele (Gruppensieg 51→55 %), ändert keinen Tipp.
- Geopolitik (Iran spielt alle Gruppenspiele in USA): nicht kalibrierbar, nur
  Sensitivität dokumentiert (Malus 0.05/0.10 → Quali 64→60/55 %). Vorzeichen unklar
  (Inglewood = LA-Diaspora). Kein Modell-Eingriff.
- `test_ko_model.py`: Verlängerungs-Term (f=0 schon in-sample!) und Elfmeter-
  Steilheits-Fit (Train will kp=1.0, Test sagt nein: 0.6485>0.6411) — BEIDE verworfen.
  Elo-Favorit gewann nur 17/31 WM-Elfmeterschießen (55 %); kp=0.25 (Δscores/4) bleibt.
- `test_matchtype_feature.py`: Match-Typ-Gewichtung (Friendlies < Quali < Turnier).
  Beste Variante −0.0003 (Rauschen); Friendlies GANZ ignorieren schadet (+0.0012, sie
  tragen Signal). Elo+Zeit-Decay greifen das schon ab. Verworfen.
- `test_h2h_feature.py`: Head-to-Head (orientierte Tordiff früherer Duelle, zeit-gew.).
  Train-optimales gamma=−0.03 (≈0, sogar leicht negativ → Mean-Reversion, NICHT
  „Angstgegner"); Gläubigen-gamma +0.20 schadet (+0.0215). Alles steckt in der Stärke.
  Verworfen — Lehrstück: RF-Feature-„importance" (Screenshot) ≠ Out-of-sample-Wert.

**Kern-Erkenntnisse (für Argumentationen):**
- `magic.py`: Favorit gewinnt 59.5 % der Einzelspiele, 16–17 % der Turniere; Titel-
  Entropie 4.0/5.6 Bit → Turnier zu ~72 % „offen". Skill-Regler k: 0→2.3 %, 1→16 %,
  4→53 %. Die „Magie" ist einkalibriert, kein fehlender Faktor.
- `test_cinderella_tail.py`: echte Sensationen hatten vorab reale Chancen
  (Marokko'22 4.2 %, Kroatien'18 12 %, Costa Rica'14 32 %, Uruguay'10 43 %, DE'02 28 %).
  ~1.8 von 4 Halbfinalisten kommen erwartungsgemäß von außerhalb der Top-8.
  → Identität des Aschenputtels unvorhersagbar, Häufigkeit korrekt abgebildet.
- `historical_brackets.py`: Brasilien war Favorit in 6 von 9 WMs seit 1990 und gewann
  keine davon (Titel nur 1994/2002, als es NICHT Favorit war).

## Dateien

```
data/
  teams_2026.csv          48 Teams × 5 Variablen (MW real, FIFA real, Elo berechnet)
  groups_2026.json        echte Gruppen A–L (aus Spielplänen rekonstruiert; F: Schweden!)
  injuries_2026.json      bekannte Ausfälle (out/doubtful) — bei News einfach editieren
  cards_2026.json         Karten je Team (Fair-Play-Tiebreaker) + bans[] (Auto-Sperren)
  calibrated_params.json  gefittete Koeffizienten (von calibrate.py geschrieben)
  raw/results.csv         martj42/international_results (~49k Spiele, inkl. 2026-Fixtures)
  raw/shootouts.csv       Elfmeter-Sieger (von snapshot.py geladen)
src/
  model.py                Kernmodell. build_scores() = Einstieg (lädt Kalibrierung,
                          Ausfälle, setzt _ATT/_DEF/_MU_EFF/_RHO/_HOST_ADV).
                          simulate_tournament(..., fixed_group=, ko_winners=) = Conditioning.
  calibrate.py            Poisson-MLE, Modellauswahl (single/decay/att-def), DC-rho,
                          EN2DE-Aliasse, load_matches(), outcome_probs(), TEST_FROM
  validate.py             ECE-Reliabilität, Elo-Backtest 2014/18/22, Champion-Backtest,
                          compute_elo_until(), fit_elo_poisson(), ELO_DENOM=400
  uncertainty.py          Bootstrap-Bänder (B=24×K=5000, ~3 min)
  calib_check.py          Momentenabgleich Torraten
  magic.py                Zufallsniveau-Quantifizierung (Skill-Regler)
  injuries.py             Ausfall-Wirkungs-Report (mit/ohne Vergleich)
  snapshot.py             LIVE-SNAPSHOTS (s. unten)
  simulate_report.py      N Turniere, Gruppenphasen-Quoten (CLI-Arg = N)
  match_predictions.py    72 Gruppenspiele analytisch: W/D/L + Score-Verteilung + Verify
  playthrough.py          EIN Turnier komplett ausspielen (CLI-Arg = Seed)
  historical_sweep.py     9 WMs 1990–2022, generischer Baum
  historical_brackets.py  9 WMs mit ECHTEN rekonstruierten Brackets
  dashboard.py            baut output/dashboard.html aus allen Output-JSONs/CSVs
  prototype.py            Ur-Prototyp (8 Teams), nur historisch
  test_*.py               Feature-Experimente (Elo angenommen, Rest verworfen)
output/
  win_probabilities_2026.csv, group_stage_2026.csv, group_fixtures.json,
  title_uncertainty.csv, tournament_myth.json, cinderella_tail.json,
  dashboard.html, snapshots/ (snapshot_*.json, history.csv, cron.log)
```

## Workflows

**Standard-Lauf nach Datenänderung:**
```bash
cd src
python3 calibrate.py          # nur nötig, wenn sich VARIABLEN/Historie ändern (~50 s)
python3 model.py              # Prognose + win_probabilities_2026.csv (~3 s)
python3 match_predictions.py  # Spielplan-JSON fürs Dashboard
python3 uncertainty.py        # Bänder (~3 min, nur bei Bedarf)
python3 dashboard.py          # Dashboard regenerieren
```
Ausfall-Update: nur `data/injuries_2026.json` editieren → `model.py` + `dashboard.py`.

**Standard nach Datenänderung: `./run_all.sh`** (Pipeline in richtiger Reihenfolge:
model → match_predictions → tippzettel → dashboard; Flags `--calibrate`, `--uncertainty`).

**Live-Snapshots (läuft automatisch):**
- Cron installiert: `45 23 * 6,7 *` UND `30 9 * 6,7 *` (Morgenlauf für die
  US-Westküsten-Spiele) → `snapshot.py`. Entfernen: `crontab -e`, Zeilen mit snapshot.py.
- **Live-Eval**: jeder Snapshot misst das EINGEFRORENE Vorturnier-Modell an den
  gespielten Spielen (Gruppen: W/D/L-LogLoss vs. Basis; K.-o.: vs. Münzwurf) →
  `live_eval` im Snapshot-JSON. Die WM ist unser erstes unberührtes Test-Set
  (heilt Test-Set-Reuse + Feature-Look-ahead der 0.985-Headline-Zahl).
- snapshot.py: lädt results.csv frisch, fixiert gespielte Spiele (Gruppen als
  Ergebnisse, K.-o. als Sieger inkl. shootouts.csv), berechnet Elo NEU (Form!),
  simuliert Rest, schreibt Snapshot + history.csv, druckt Diff (⚡AUSBRUCH ab Δ≥3 Pt).
  Idempotent: ohne neue gespielte Spiele kein neuer Snapshot. `--force`, `--no-download`.
- Baseline-Snapshot vor Turnierstart existiert (0 Spiele).

**Dashboard-Datenquelle:** `dashboard.py` bevorzugt `output/live_probabilities.csv`
(vom Snapshot konditioniert geschrieben, inkl. Live-Elo + Stärke) sobald `n_played>0`,
sonst die statische `win_probabilities_2026.csv` (model.py). „Stand"-Banner zeigt
Live vs. Vorturnier. So zeigen Ranking, Team-Details und Titelrennen-Chart denselben
konditionierten Stand. launchd-Wrapper baut das Dashboard nach jedem Snapshot neu.

**Dashboard** (`output/dashboard.html`, offline, self-contained): Rangliste mit
Metrik-Umschalter, Spielplan mit W/D/L-Balken + aufklappbarer Score-Verteilung,
Team-Details (Elo, Band, 🚑 Ausfälle, Schmunzler), Modell-vs-ESPN-Experten,
Mythos-Check (Turniermannschaft), Aschenputtel-Sektion, Orakel-Button, Gruppen.

## Konventionen & Stolperfallen

- **Nur Python-Standardbibliothek** (kein numpy — bewusst, läuft überall).
- Teamnamen: DE-ASCII-Keys (`Suedkorea`, `Tuerkei`...) in Daten; `NICE`-Dicts für
  Anzeige; `calibrate.ALIASES`/`EN2DE` mappt results.csv-Namen (EN) → DE-Keys.
  1990 heißt Westdeutschland im Datensatz „Germany".
- `play_group()` gibt **3-Tupel** zurück (ranked, stats, res).
- `build_scores(teams, use_ratings=True, apply_injuries=True)` setzt globale
  Tormodell-Parameter als Seiteneffekt — vor jedem `model.run()` aufrufen.
- `match_goals(a, b)` ist 2-argumentig (nutzt globale _ATT/_DEF).
- Kalibrier-Koeffizienten NIE wegen 2026-Inputänderungen neu fitten (Ausfälle etc.
  ändern nur Inputs); neu fitten nur bei neuen Variablen oder neuer Historie.
- z-Standardisierung läuft über das 48er-Feld → Inputänderung eines Teams verschiebt
  alle z-Scores minimal (bekannt, akzeptiert).
- Webfetch: spiegel.de und transfermarkt.com sind **blockiert** (User lieferte
  Inhalte als Paste/Screenshot). eloratings.net nicht nötig (Elo lokal berechnet).
- Einzelspiel-Wahrscheinlichkeiten **analytisch** rechnen (match_probs /
  score_distribution), nicht simulieren; simulieren nur fürs Turnier-Aggregat.
- Es existieren ZWEI Browser-Verbindungen (Auswahl nötig bei Screenshots).
- Sprache: Antworten auf Deutsch; User mag keine Gedankenstrich-Lawinen.

## Offene/legitime nächste Schritte

- ~~Titelrennen-Chart~~ ERLEDIGT: dashboard.py rendert SVG aus history.csv automatisch
  (Sektion „Titelrennen über die Zeit", erscheint ab 2 Snapshot-Ständen).
- Späte Ausfälle: injuries_2026.json pflegen (Ein-Zeilen-Edit) → danach `./run_all.sh`.
- KO-Phase: knockout-Paarungen werden erst nach Gruppenende fix → dann ggf.
  match_predictions auf R32 erweitern (Paarungen stehen dann in results.csv).
- 3 Marktwerte (USA/Uruguay/Kroatien) und ~13 FIFA-Punkte kleiner Teams sind
  weiterhin Schätzungen — Politur, kein Hebel.
