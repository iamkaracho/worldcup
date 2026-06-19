# Modellplanung — WM-Sieger-Prognose nach Klement

> Rekonstruktion und Implementierung des Prognosemodells von Ökonom Joachim Klement
> (SPIEGEL, 03.06.2026). Klement sagte die letzten drei Weltmeister korrekt voraus
> (2014 DE, 2018 FR, 2022 AR) und tippt für 2026 die **Niederlande**.

---

## 0. Geist des Projekts

Klement baute das Modell ursprünglich, um zu **zeigen, dass solche Prognosen nicht
funktionieren** — und behielt dreimal recht. Wir bauen es im selben Geist: kein
Wettsystem, sondern ein nachvollziehbares, ehrliches Modell, das seine eigene
Unsicherheit explizit macht. „Wer darauf Geld setzt, dem ist nicht zu helfen."

Konsequenz für das Design: Der **Zufallsfaktor ist kein Schönheitsfehler, sondern
Kernbestandteil**. Das Modell liefert Wahrscheinlichkeiten, keine Gewissheiten.

---

## 1. Ziel & Output

**Ziel:** Aus wenigen, öffentlich verfügbaren Länder-Variablen einen Stärke-Score je
Team ableiten, daraus paarweise Siegwahrscheinlichkeiten bilden und den kompletten
Turnierbaum per Monte-Carlo-Simulation ausspielen.

**Outputs:**
- Weltmeister-Wahrscheinlichkeit je Team (P(Titel))
- Erwartete Runde des Ausscheidens je Team
- Ein „modaler" Turnierbaum (wahrscheinlichster einzelner Verlauf) — analog zu
  Klements Aussage „DE trifft im Achtelfinale auf Frankreich"
- Sensitivitätsanalyse: Wie stabil ist der Tipp gegenüber dem Zufallsfaktor?

---

## 2. Variablen (1:1 aus dem Artikel)

| # | Variable | Proxy / Operationalisierung | Quelle |
|---|----------|------------------------------|--------|
| 1 | **Wohlstand** (Infrastruktur) | BIP pro Kopf (PPP) | World Bank / IMF |
| 2 | **Bevölkerungsgröße** | Einwohnerzahl | World Bank / UN |
| 3 | **Verankerung des Fußballs** | Registrierte Spieler / Vereine pro Kopf; ersatzweise Popularitäts-Index | FIFA Big Count, Proxy |
| 4 | **Weltranglistenposition** | FIFA-Ranking-Punkte (nicht nur Rang) | FIFA |
| 5 | **Zufallsfaktor** | Stochastischer Term je Spiel | Modellintern |

**Hinweise zur Operationalisierung:**
- Variablen 1–2 haben *abnehmenden Grenznutzen* → log-transformieren
  (Doppelte Bevölkerung ≠ doppelte Stärke).
- Variable 4 (FIFA-Punkte) ist der stärkste Einzelprädiktor und sollte das höchste
  Gewicht bekommen; 1–3 erklären „strukturelles Potenzial", 4 die aktuelle Form.
- Variable 3 ist datentechnisch am heikelsten (FIFA Big Count ist veraltet/lückenhaft)
  → als Risiko markiert, ggf. durch Liga-Stärke-Proxy ersetzen.

---

## 3. Modellarchitektur

```
Rohdaten je Land
   │  (normalisieren, log-transformieren, z-standardisieren)
   ▼
Feature-Vektor x_i  ──►  Stärke-Score  S_i = w·x_i        (gewichtete Linearkombination)
   │
   ▼
Paar-Wahrscheinlichkeit:  P(i schlägt j) = logistic( (S_i − S_j) / τ )
   │                                                   (τ = Temperatur/Zufallsfaktor)
   ▼
Monte-Carlo-Turniersimulation (N = 50.000 Durchläufe über den echten Spielplan)
   │
   ▼
Aggregierte Wahrscheinlichkeiten + modaler Turnierbaum
```

**Designentscheidungen:**
- **Logistische Paarfunktion** statt fixer Regeln → glatte Wahrscheinlichkeiten,
  Underdogs können gewinnen.
- **Temperatur τ = Klements Zufallsfaktor.** τ→0: stärkeres Team gewinnt fast immer
  (langweilig, unrealistisch). τ groß: reiner Zufall. τ wird per Backtest kalibriert.
- **Echter Spielplan / Bracket** ist Pflicht — sonst keine Aussagen wie „DE–FR im
  Achtelfinale". Gruppenphase → K.-o.-Baum exakt abbilden.
- **Unentschieden** in der Gruppenphase modellieren (3-Wege-Ausgang), in K.-o.-Runden
  Verlängerung/Elfmeter als zusätzliches Zufallselement.

---

## 4. Kalibrierung & Validierung (das Herzstück)

Klements Glaubwürdigkeit kommt aus 3/3 Treffern. Wir replizieren das als **Backtest**:

1. **Out-of-sample-Backtest** gegen WM 2014, 2018, 2022:
   - Modell *nur* mit Daten *vor* dem jeweiligen Turnier füttern.
   - Gewichte `w` und Temperatur `τ` auf 2014+2018 fitten, auf 2022 testen
     (bzw. Leave-one-out).
2. **Metriken:** Brier-Score / Log-Loss auf Match-Ebene, nicht nur „Sieger getroffen".
   (Ein Modell, das den Sieger trifft, aber sonst unsinnig ist, fällt hier durch.)
3. **Ehrlichkeits-Check:** Wenn das Modell den Titelträger mit z. B. nur 12 %
   Wahrscheinlichkeit ausweist, ist „3/3 richtig" v. a. Glück — genau Klements Punkt.
   Das dokumentieren wir explizit statt es zu verstecken.
4. **Sensitivität:** Tipp-Stabilität über τ und über Bootstrap der Gewichte.

---

## 5. Projektstruktur (Vorschlag)

```
modell/
├── MODELLPLANUNG.md          # dieses Dokument
├── data/
│   ├── raw/                  # World-Bank-, FIFA-Rohdaten
│   └── processed/teams.csv   # Feature-Tabelle je Team
├── src/
│   ├── features.py           # Einlesen, Transformieren, Standardisieren
│   ├── strength.py           # Stärke-Score (Variable 1–4)
│   ├── match.py              # logistische Paar-Wahrscheinlichkeit + Zufall
│   ├── tournament.py         # Spielplan/Bracket + K.-o.-Logik
│   ├── simulate.py           # Monte-Carlo-Loop, Aggregation
│   └── calibrate.py          # Backtest 2014/18/22, Fit von w und τ
├── config/
│   ├── weights.yaml          # Gewichte w, Temperatur τ
│   └── bracket_2026.yaml     # Gruppen + K.-o.-Baum WM 2026
├── notebooks/                # Explorative Analyse, Plots
└── output/
    ├── win_probabilities.csv
    └── modal_bracket.txt
```

Empfohlener Stack: **Python** (pandas, numpy, scipy/optuna für Kalibrierung,
matplotlib). Bewusst schlank — Klements Modell ist „kein Hexenwerk".

---

## Stand der Umsetzung (03.06.2026)

- ✅ **M1–M3 gebaut** für 2026: `src/model.py` simuliert alle 48 Teams über das echte
  Format (12 Gruppen, beste 8 Dritte, K.-o.-Baum). Daten in `data/teams_2026.csv` +
  `data/groups_2026.json` (illustrativ). Output: `output/win_probabilities_2026.csv`.
- ✅ **Poisson-Tormodell** statt reiner Paar-Logistik → realistische Streuung
  (Favorit ~17 %, langer Tail) und echte Tordifferenz für das Dritten-Ranking.
- ✅ **M4 Kalibrierung umgesetzt**: `src/calibrate.py` schätzt Gewichte + Steilheit
  gemeinsam per **Poisson-Regression** auf 1008 echten Länderspielen (≥2018,
  `data/raw/results.csv`). Parameter → `data/calibrated_params.json`, das `model.py`
  automatisch lädt (Modus „kalibriert"). Torniveau zusätzlich momenten­geprüft
  (`src/calib_check.py`).
- ✅ **Validierung**: Out-of-sample (153 Spiele ab 2025) Ergebnis-Log-Loss
  **1.003 vs. Basisrate 1.085** → das Modell schlägt die naive Basisrate
  (mit echten Marktwerten von 1.016 auf 1.003 verbessert).
- 💡 **Empirischer Befund**: Kalibriert dominieren **Marktwert (~48 %)** und
  **FIFA-Punkte (~45 %)**; **Wohlstand (BIP) und Bevölkerung tragen ~0 %** bei.
  Klements strukturelle Variablen sind also kaum prädiktiv, sobald Marktwert + Ranking
  im Modell sind — ein Ergebnis, das nur die Kalibrierung sichtbar macht.

## Finale Lage vor Turnierstart (2 Tage vorher)

- ✅ **Ausfälle eingepflegt** (`data/injuries_2026.json`, `src/injuries.py`): bekannte
  Verletzungen/Absagen (Rodrygo, Estêvão, Militão, Palmer, Grealish, Simons, Timber,
  Mitoma, Ekitiké, Gnabry …) werden vom Kader-Marktwert abgezogen, „doubtful" (Yamal,
  Neymar, Davies) zu 50 %. Re-Kalibrierung nicht nötig — nur die 2026-Inputs ändern sich.
  Effekt: moderat (meist <1 Pt), da Elo (ergebnisbasiert) als Ballast wirkt; größter
  Effekt **relativ** — unverletzte Teams (Argentinien, Deutschland) gewinnen.
  Kader = fix, Verletzungen = größtenteils gesetzt, Start-XI bewusst nicht modelliert.

## Geschlossene Lücken (Stand final)

- ✅ **Echte Variablenwerte**: FIFA-Punkte real (FIFA-Rangliste April/Juni 2026) und
  **Kader-Marktwerte real (Transfermarkt, WM 2026)** für alle 48 Teams.
  `data/teams_2026.csv`. (USA/Uruguay/Kroatien teils Näherung.)
- ✅ **Echte Gruppen** aus den 2026-Spielplänen rekonstruiert; **Gruppe F korrigiert:
  Schweden** (UEFA-Playoff-Sieger) statt des Platzhalters Bolivien.
- ✅ **Reliabilität (Stufe C)**: `src/validate.py` → ECE **0.031** (gut kalibriert).
- ✅ **Historischer Backtest** gegen WM 2014/2018/2022 (zeitkorrektes Elo, kein
  Look-ahead): Modell schlägt in **allen drei** Turnieren die Basisrate.
- ✅ **Offizieller FIFA-K.-o.-Baum** (Spiele 73–104) inkl. Annex-C-Zuordnung der
  besten 8 Gruppendritten (Bipartit-Matching) — ersetzt die Stärke-Setzliste.
  Korrektheits-Check: Deutschland (Sieger E) und Frankreich (Sieger I) treffen
  laut Baum im **Achtelfinale** aufeinander — exakt wie im Artikel beschrieben.
- ✅ **Dixon-Coles-Korrektur** (ρ=−0.06): modelliert knappe Remis korrekt; hebt die
  simulierte Remisquote von 23.8 % auf 25.1 % (Zielband) und senkt den Out-of-sample-
  Log-Loss auf **1.001**. Übernommen nur, weil es sich out-of-sample auszahlt.
- ✅ **Parameter-Unsicherheit** (`src/uncertainty.py`): Bootstrap der Kalibrierung →
  90 %-Band je Titel-Wahrscheinlichkeit (Frankreich 15.8 % [14.2–17.4]). Trennt
  Schätz- von Monte-Carlo-Unsicherheit — Klements Punkt, sauber quantifiziert.
- ✅ **Angriff/Abwehr-Split + Zeitgewichtung** (A.1+A.2): `calibrate.py` vergleicht
  vier Varianten out-of-sample und wählt **att/def+decay** (Log-Loss 1.0015, mit DC
  **0.9998**). Befund: Marktwert treibt den Angriff, FIFA-Punkte die Abwehr.
- ✅ **Heimvorteil** der Gastgeber (Tier C): gefittete +0.15 log-Tore/Heimspiel für
  USA/Mexiko/Kanada (`HOST_BONUS=None` nutzt den kalibrierten Wert).
- ✅ **FIFA-Direktvergleich** als Gruppen-Tiebreaker (Tier C) statt reinem Zufall.
- ✅ **Champion-Backtest** (`validate.py`, Tier B): echte Sieger 2014/18/22 auf Rang
  4/4/2, mittlere Ignoranz 3.05 bit < 5.0 uniform. Volle Posterior-Näherung liefert
  bereits der Bootstrap (`uncertainty.py`).
- ✅ **Elo als 5. Variable** (`src/test_elo_feature.py` → übernommen): World-Football-Elo
  (eloratings.net-Methode, lokal aus `results.csv`) als zusätzliches Feature senkt den
  Out-of-sample-Log-Loss **0.9998 → 0.9850**. Trotz r=0.90 zur FIFA-Rangliste trägt es
  orthogonale Info; im Modell wird Elo zum stärksten Abwehr-Signal und verdrängt die
  FIFA-Punkte fast. (Erst als *Ersatz* getestet → verworfen; als *Zusatz* → Gewinn.)
- 🧪 **Verworfen (Disziplin)**: (a) ergebnisbasiertes Team-Rating als *Ersatz* der Struktur
  (`src/rating.py`); (b) **Kader-Durchschnittsalter** als 6. Variable (`src/test_age_feature.py`)
  — 0.9931 → 0.9942; (c) **GOAT-/Star-Faktor** (`src/test_goat_feature.py`): Top-Spieler-Wert
  (0.9967) und Star-Konzentration (0.9990) beide schlechter — Starpower steckt schon im
  Marktwert/Elo. Alle drei redundant → nicht übernommen.
- 🧪 **„Turniermannschaft"-Effekt verworfen** (`src/test_tournament_team.py`): team-
  spezifischer Turnier-Bonus (Elo-Punkte), geschrumpft, Leave-one-tournament-out getestet.
  *In-sample* perfekt zum Narrativ (Frankreich +113, Niederlande +96 als Überperformer;
  Brasilien −109, Spanien −88, Argentinien −80 als „Choker") — *out-of-sample* macht es die
  Vorhersage in **allen drei** Turnieren schlechter (0.978 → 1.000). Reines Hindsight-Rauschen
  aus Mini-Stichproben. Die schärfste Bestätigung von Klements These im ganzen Projekt.
- ✅ **Tail-/Varianz-Kalibrierung bestätigt** (`src/test_cinderella_tail.py`): das Modell
  erwartet ~1,8 von 4 Halbfinalisten von außerhalb der Top-8 und hätte echten Sensationen
  vorab reale (kleine) Chancen gegeben — Marokko 2022 4,2 %, Kroatien 2018 12 %, Costa Rica
  2014 32 %. Es kann das Aschenputtel nicht *benennen* (vgl. Turnier-Bonus-Test), aber es
  schließt es nie aus. Identität ≠ vorhersagbar, Häufigkeit = korrekt abgebildet.
- ✅ **„Modell vs. Mensch"** (Dashboard): Vergleich unseres Rangs mit ESPNs Experten-Panel.
  Top-4 (Spanien/Frankreich/Argentinien/England) deckungsgleich → robust; Divergenzen bei
  Brasilien (+3), Marokko (+5, Experten-Geheimtipp), Niederlande (−2) markieren die blinden
  Flecken des Modells (Form/Verletzungen/Momentum). ESPNs eigenes Kader-Modell = Elo+Marktwert,
  also unser Zwilling — externe Bestätigung des Ansatzes.

## 6. Roadmap

| Phase | Inhalt | Ergebnis |
|-------|--------|----------|
| **M1 — Daten** | Variablen 1–4 für alle 48 Teilnehmer 2026 sammeln, `teams.csv` | saubere Feature-Tabelle |
| **M2 — Score** | Stärke-Score + Paar-Wahrscheinlichkeit implementieren | `S_i`, `P(i>j)` plausibel |
| **M3 — Turnier** | Spielplan 2026 + Monte-Carlo-Simulation | erste P(Titel)-Tabelle |
| **M4 — Kalibrierung** | Backtest 2014/18/22, `w` & `τ` fitten | belegte Trefferquote + Brier-Score |
| **M5 — Auswertung** | Sensitivität, modaler Baum, Doku | reproduzierbarer 2026-Tipp |

**Akzeptanzkriterium:** Modell reproduziert im Leave-one-out-Backtest mind. die
Finalteilnehmer von 2018 und 2022 mit überdurchschnittlicher Wahrscheinlichkeit —
*und* dokumentiert ehrlich, wie viel davon Zufall ist.

---

## 7. Risiken & Grenzen

- **Variable 3 (Fußball-Verankerung)** schlecht datenverfügbar → größte Modellschwäche;
  Fallback-Proxy definieren (z. B. Marktwert-Summe des Kaders / Anteil Spieler in Top-5-Ligen).
- **Overfitting:** Nur 3 Turniere als „Ground Truth" für den Titel → extrem kleine
  Stichprobe. Deshalb Match-Level-Metriken statt Titel-Trefferquote als Hauptkriterium.
- **Strukturbruch 2026:** 48 statt 32 Teams, neuer Modus, drei Gastgeber (USA/MEX/CAN).
  Backtest-Bracket-Logik ≠ 2026-Bracket-Logik → sauber trennen.
- **Survivorship-Bias der Story:** „3/3 richtig" ist erzählerisch stark, statistisch
  dünn. Das Modell soll diese Demut bewahren, nicht verkaufen.

---

## 8. Offene Entscheidungen (für dich)

1. **Sprache/Stack:** Python wie vorgeschlagen — oder R / etwas anderes?
2. **Variable 3:** FIFA Big Count versuchen oder direkt Marktwert-Proxy nehmen?
3. **Tiefe:** Reicht der WM-2026-Tipp, oder soll der volle Backtest 2014/18/22 mit
   sauberer Validierung gebaut werden (deutlich mehr Datenarbeit)?
4. **Datenbeschaffung:** Manuell kuratiert (klein, kontrolliert) vs. APIs anzapfen?
```
