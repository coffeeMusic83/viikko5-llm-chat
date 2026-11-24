#!/usr/bin/env bash
# Week 5 deployment script.
#
# Installed once by hand as /usr/local/sbin/viikko5-deploy (root:root, 755).
# GitHub Actions copies the repository to /home/deploy/incoming/viikko5 and runs:
#     sudo /usr/local/sbin/viikko5-deploy <github.sha>
# The deploy user may run only this one command with sudo (/etc/sudoers.d/viikko5-deploy).
set -euo pipefail

SHA="${1:-}"
SRC=/home/deploy/incoming/viikko5
BASE=/opt/viikko5
APP_DIR=$BASE/app
VENV=$BASE/venv
SERVICE=viikko5
UNIT_DST=/etc/systemd/system/viikko5.service
NGINX_DST=/etc/nginx/snippets/viikko5.conf
HEALTH_URL=http://127.0.0.1/viikko5/health

log() { echo "[deploy] $*"; }
fail() { echo "[deploy] ERROR: $*" >&2; exit 1; }

[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "usage: viikko5-deploy <40-character commit SHA>"
[[ -f "$SRC/wsgi.py" && -d "$SRC/chat" ]] || fail "application source not found in $SRC"
id viikko5 >/dev/null 2>&1 || fail "service user viikko5 does not exist"

log "deploying commit $SHA"

log "1/7 copy the code to $APP_DIR"
install -d -o root -g viikko5 -m 750 "$BASE" "$APP_DIR"
rsync -a --delete --chown=root:viikko5 --chmod=D750,F640 \
  "$SRC/chat" "$SRC/docs" "$SRC/wsgi.py" "$SRC/requirements.txt" "$APP_DIR/"
echo "$SHA" > "$APP_DIR/REVISION"
chown root:viikko5 "$APP_DIR/REVISION"
chmod 640 "$APP_DIR/REVISION"

log "2/7 install dependencies into $VENV"
[[ -x "$VENV/bin/pip" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$APP_DIR/requirements.txt"

log "3/7 database schema (CREATE ... IF NOT EXISTS)"
mariadb < "$SRC/db/schema.sql"

log "4/7 systemd unit"
install -m 644 -o root -g root "$SRC/deploy/viikko5.service" "$UNIT_DST"
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"

log "5/7 nginx snippet (tested before reload)"
backup=""
if [[ -f "$NGINX_DST" ]]; then
  backup=$(mktemp)
  cp -p "$NGINX_DST" "$backup"
fi
install -m 644 -o root -g root "$SRC/deploy/nginx-viikko5.conf" "$NGINX_DST"
if ! nginx -t; then
  if [[ -n "$backup" ]]; then cp -p "$backup" "$NGINX_DST"; else rm -f "$NGINX_DST"; fi
  fail "nginx -t failed, the previous configuration was restored and nginx was not reloaded"
fi
[[ -n "$backup" ]] && rm -f "$backup"
systemctl reload nginx

log "6/7 restart only $SERVICE.service"
systemctl restart "$SERVICE"

log "7/7 verify that the new version is running"
for i in $(seq 1 30); do
  body=$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null || true)
  if [[ "$body" == *"\"$SHA\""* ]]; then
    log "OK: $HEALTH_URL returns $SHA (attempt $i)"
    # Keep the installed script in sync with the repository (takes effect next run).
    install -m 755 -o root -g root "$SRC/deploy/deploy.sh" /usr/local/sbin/viikko5-deploy
    exit 0
  fi
  sleep 2
done

systemctl status "$SERVICE" --no-pager -l | tail -20 || true
fail "health check did not return $SHA"
