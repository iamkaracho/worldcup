#!/bin/zsh
# Wird von launchd (com.modell.wmsnapshot) 09:30 + 23:45 aufgerufen.
# launchd holt verpasste Termine beim Aufwachen nach (anders als cron).
# Snapshot (laedt Ergebnisse, fixiert, Elo neu, simuliert) + Dashboard-Rebuild.
DIR="$(dirname "$0")/src"
LOG="$(dirname "$0")/output/snapshots/cron.log"
PY="$(command -v python3)"
cd "$DIR" || exit 1
echo "--- $(date '+%Y-%m-%d %H:%M:%S') launchd-Lauf ---" >> "$LOG"
"$PY" snapshot.py  >> "$LOG" 2>&1
"$PY" dashboard.py >> "$LOG" 2>&1
