#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/root/digibytewallet-org-github
ARCHIVE=/root/dgb-newsroom-engine-v01.tgz
STAGE=/root/dgb-newsroom-engine-install
ENGINE=/opt/dgb-newsroom-engine

[ "$(id -u)" -eq 0 ] || { echo 'ERROR: Must run as root on configured DigiByte VM'; exit 1; }
test -f "$ARCHIVE"
test -d "$REPO/.git"

printf '\n========== INSTALL PRIVATE RESEARCH ENGINE ==========\n'
mkdir -p "$STAGE" "$ENGINE"
tar -xzf "$ARCHIVE" -C "$STAGE"
cd "$STAGE/src"
python3 -m unittest discover -s tests -v
python3 -m py_compile engine.py

if ! getent passwd dgbnews >/dev/null; then
  useradd --system --home-dir /var/lib/dgb-newsroom-engine --shell /usr/sbin/nologin dgbnews
fi
install -d -m 0700 -o dgbnews -g dgbnews /var/lib/dgb-newsroom-engine
cp -f "$STAGE/src/engine.py" "$STAGE/src/dashboard.html" "$STAGE/src/sources.json" "$STAGE/src/README.md" "$ENGINE/"
chmod 755 "$ENGINE"
chmod 644 "$ENGINE"/engine.py "$ENGINE"/dashboard.html "$ENGINE"/sources.json "$ENGINE"/README.md
chown -R root:root "$ENGINE"

echo '========== INSTALL SANDBOXED BACKGROUND SERVICE =========='
cat > /etc/systemd/system/dgb-newsroom-engine.service <<'UNIT'
[Unit]
Description=Private DigiByte Newsroom source monitor and editorial story queue
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=dgbnews
Group=dgbnews
WorkingDirectory=/opt/dgb-newsroom-engine
Environment=DGB_ENGINE_STATE=/var/lib/dgb-newsroom-engine
Environment=DGB_ENGINE_PORT=8770
ExecStart=/usr/bin/python3 /opt/dgb-newsroom-engine/engine.py serve
Restart=on-failure
RestartSec=4
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectHome=true
ProtectSystem=strict
ProtectControlGroups=true
ProtectKernelTunables=true
RestrictSUIDSGID=true
ReadWritePaths=/var/lib/dgb-newsroom-engine
MemoryMax=256M
TasksMax=35
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now dgb-newsroom-engine.service
systemctl restart dgb-newsroom-engine.service
READY=0
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8770/api/health -o /dev/null 2>/dev/null; then READY=1; break; fi
  sleep 1
done
if [ "$READY" != 1 ]; then
  journalctl -u dgb-newsroom-engine -n 50 --no-pager
  echo 'ERROR: Engine is not responding'; exit 1
fi
ss -ltn | awk '{print $4}' | grep -qx '127.0.0.1:8770'
echo 'PASS: New engine runs as unprivileged dgbnews on localhost only'

printf '\n========== CONNECT TO PASSWORD-PROTECTED ARTICLE EDITOR ==========\n'
cd "$REPO"
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain --untracked-files=all)"
git fetch --quiet origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
python3 "$STAGE/installer/patch-editor.py"
python3 -m py_compile tools/newsroom-editor.py

git add -- tools/newsroom-editor.py
git diff --cached --check
if ! git diff --cached --quiet; then
  test "$(git diff --cached --name-only)" = 'tools/newsroom-editor.py'
  git commit -m 'Connect private story radar to newsroom draft review'
  git push origin main
fi
systemctl restart dgb-newsroom-editor.service
READY=0
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8769/login -o /dev/null 2>/dev/null; then READY=1; break; fi
  sleep 1
done
if [ "$READY" != 1 ]; then
  journalctl -u dgb-newsroom-editor -n 30 --no-pager
  echo 'ERROR: Existing editor not responding'; exit 1
fi
ss -ltn | awk '{print $4}' | grep -qx '127.0.0.1:8769'
test -z "$(git status --porcelain --untracked-files=all)"

echo '========== STATUS =========='
systemctl --quiet is-active dgb-newsroom-engine.service
systemctl --quiet is-active dgb-newsroom-editor.service
printf 'PASS: Private monitoring engine and existing editor are both active\n'
printf 'Public website and faucet untouched; automated public publishing disabled.\n'
printf 'Public editor GitHub HEAD: %s\n' "$(git rev-parse --short HEAD)"
rm -rf "$STAGE" "$ARCHIVE"
