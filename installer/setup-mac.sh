#!/usr/bin/env bash
set -Eeuo pipefail
BASE="$HOME/Library/Application Support/DigiByte Newsroom"
APP="$HOME/Desktop/DigiByte Newsroom.app"
mkdir -p "$BASE"

printf '\n========== UPGRADE EXISTING ONE-CLICK MAC APP ==========\n'
cat > "$BASE/connect.sh" <<'SCRIPT'
#!/bin/bash
set -Eeuo pipefail
ready() {
  /usr/bin/curl -fsS --max-time 3 "http://127.0.0.1:$1/$2" 2>/dev/null | /usr/bin/grep -Fq "$3"
}
connect() {
  local localport="$1" remoteport="$2" path="$3" marker="$4"
  if ready "$localport" "$path" "$marker"; then return; fi
  if /usr/sbin/lsof -nP -iTCP:"$localport" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $localport is in use by something other than DigiByte Newsroom";exit 1
  fi
  /usr/bin/ssh -f -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${localport}:127.0.0.1:${remoteport}" \
    root@64.23.176.29 </dev/null >/dev/null 2>&1 || {
      echo "Could not establish secure SSH tunnel on local port $localport";exit 1;
    }
  local i
  for i in $(seq 1 24); do
    if ready "$localport" "$path" "$marker"; then return; fi
    sleep 0.4
  done
  echo "SSH connected but localhost:$localport is not serving the newsroom"
  exit 1
}
connect 8877 8769 login 'DigiByte Newsroom'
connect 8878 8770 '' 'DigiByte Wallet · Story Radar'
SCRIPT
chmod 700 "$BASE/connect.sh"
cat > "$BASE/DigiByte Newsroom.applescript" <<'APPLESCRIPT'
on run
    set launcher to (POSIX path of (path to home folder)) & "Library/Application Support/DigiByte Newsroom/connect.sh"
    try
        do shell script (quoted form of launcher)
        open location "http://127.0.0.1:8878/"
    on error errText
        display dialog "Could not open DigiByte Newsroom." & return & return & errText buttons {"OK"} default button "OK" with icon caution
    end try
end run
APPLESCRIPT
/usr/bin/osacompile -o "$APP" "$BASE/DigiByte Newsroom.applescript"
test -d "$APP"
echo 'PASS: Desktop app now opens Story Radar and also connects the existing Article Editor'
/usr/bin/open "$APP"
