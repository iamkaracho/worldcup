#!/bin/zsh
# Standard-Pipeline nach jeder Datenaenderung (injuries_2026.json, teams_2026.csv).
# Erzwingt die richtige Reihenfolge, damit keine Artefakte veralten.
#   ./run_all.sh                normale Pipeline (~30 s)
#   ./run_all.sh --calibrate    zusaetzlich Neu-Kalibrierung (nur bei neuen
#                               Variablen/Historie noetig, ~50 s)
#   ./run_all.sh --uncertainty  zusaetzlich Bootstrap-Baender (~3 min)
set -e
cd "$(dirname "$0")/src"

[[ "$*" == *--calibrate* ]] && { echo "== calibrate =="; python3 calibrate.py; }
echo "== model ==";             python3 model.py | tail -3
echo "== match_predictions =="; python3 match_predictions.py | tail -1
echo "== tippzettel ==";        python3 tippzettel.py | tail -1
[[ "$*" == *--uncertainty* ]] && { echo "== uncertainty =="; python3 uncertainty.py | tail -1; }
echo "== dashboard ==";         python3 dashboard.py | tail -1
echo "✓ Pipeline konsistent."
