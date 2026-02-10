#!/usr/bin/env bash
set -euo pipefail

HOST="root@ares.io"
REPO_DIR="/home/trains/trains"

echo "Deploying trains..."

echo "Pulling latest code..."
ssh "$HOST" "sudo -u trains bash -c 'cd $REPO_DIR && git pull'"

echo "Installing dependencies..."
ssh "$HOST" "sudo -u trains bash -c 'cd $REPO_DIR && /home/trains/.local/bin/uv sync'"

echo "Syncing systemd service file..."
ssh "$HOST" "cp $REPO_DIR/trains.service /etc/systemd/system/trains.service && systemctl daemon-reload"

echo "Restarting service..."
ssh "$HOST" "systemctl restart trains"

echo "Waiting for service to start..."
sleep 2

if ssh "$HOST" "systemctl is-active --quiet trains"; then
    echo "Deploy successful! Service is running."
else
    echo "Deploy failed! Service is not running."
    ssh "$HOST" "systemctl status trains"
    exit 1
fi
