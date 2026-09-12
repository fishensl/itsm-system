#!/usr/bin/env bash
set -euo pipefail
APP_DIR=$(realpath "${1:?请指定已部署的 ITSM 目录}")
[[ "$APP_DIR" != *$'\n'* && "$APP_DIR" != *' '* && "$APP_DIR" != *'%'* ]] || { echo '不支持该部署路径'; exit 1; }
[[ -f "$APP_DIR/scripts/notification_worker.py" && -x "$APP_DIR/venv/bin/python" ]] || exit 1
SERVICE_USER=$(systemctl show itsm -p User --value)
[[ -n "$SERVICE_USER" ]] || SERVICE_USER=itsm
cat > /etc/systemd/system/itsm-notifications.service <<EOF
[Unit]
Description=ITSM notification outbox consumer
After=network.target postgresql.service itsm.service
[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/scripts/notification_worker.py
Restart=always
RestartSec=5
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now itsm-notifications
