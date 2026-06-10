#!/usr/bin/env bash
#
# Watchdog sederhana — jalankan bot terus, restart otomatis kalau mati.
# Berguna di lingkungan yang TIDAK punya systemd. Untuk server dengan systemd,
# pakai x-tracker.service.
#
# Pakai:
#   ./run-forever.sh
#   nohup ./run-forever.sh >/dev/null 2>&1 &   # jalan di background
#
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/.venv/bin/python"
LOG="$DIR/tracker.log"

echo "[run-forever] mulai $(date)" >> "$LOG"
while true; do
  "$PY" "$DIR/tracker.py" >> "$LOG" 2>&1
  code=$?
  echo "[run-forever] tracker.py berhenti (exit $code) pada $(date) — restart dalam 30 detik" >> "$LOG"
  sleep 30
done
