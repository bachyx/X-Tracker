#!/usr/bin/env bash
#
# setup-oracle.sh — pasang x-tracker sebagai service systemd di VM Oracle Cloud
# (Ubuntu, ARM/Ampere atau AMD). Jalankan SEKALI di dalam VM, dari dalam folder
# x-tracker:
#
#     cd ~/x-tracker
#     bash deploy/setup-oracle.sh
#
# Script ini idempoten — aman dijalankan ulang.
set -euo pipefail

# Folder x-tracker = induk dari folder deploy/ tempat script ini berada.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(id -un)"
PYBIN="$APP_DIR/.venv/bin/python"
SERVICE_NAME="x-tracker"

echo ">> App dir : $APP_DIR"
echo ">> User    : $RUN_USER"

echo ">> [1/4] Memasang paket sistem (python venv, pip)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo ">> [2/4] Membuat virtualenv & memasang dependensi..."
if [ ! -d "$APP_DIR/.venv" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo ">> [3/4] Memeriksa config.json..."
if [ ! -f "$APP_DIR/config.json" ]; then
  echo "!! config.json belum ada. Salin config.example.json -> config.json lalu isi"
  echo "!! (cookies auth_token & ct0, targets, discord_webhook) sebelum start service."
fi

echo ">> [4/4] Membuat & mengaktifkan service systemd '$SERVICE_NAME'..."
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=x-tracker — pantau following akun X dan kirim notif Discord
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=$PYBIN $APP_DIR/tracker.py
Restart=always
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo
echo ">> SELESAI. Service '$SERVICE_NAME' aktif & auto-start saat boot."
echo ">> Lihat log : journalctl -u $SERVICE_NAME -f"
echo ">> Status    : systemctl status $SERVICE_NAME"
echo ">> Restart   : sudo systemctl restart $SERVICE_NAME"
