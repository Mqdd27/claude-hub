#!/bin/bash
# Set up (or update) both sides. Safe to re-run.
#   Mac:    two launchd jobs that rsync history + CLAUDE.md files to the server
#   Server: digest.py + systemd timer + claude-context skill linked into each agent
set -euo pipefail
cd "$(dirname "$0")"
[ -f config.env ] || { echo "config.env missing: cp config.env.example config.env and edit it"; exit 1; }
source config.env
: "${SERVER:?}" "${CTX_ROOT:?}" "${INTERVAL:=300}" "${EXCLUDE_DIRS:=}" "${SKILL_DIRS:=}"

SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"
HUB=claude-hub   # on the server: ~/claude-hub

python3 digest.py --check

# --- server -----------------------------------------------------------------
$SSH "$SERVER" "mkdir -p ~/$HUB/data ~/$HUB/ctx ~/.config/systemd/user"
rsync -az -e "$SSH" digest.py skill "$SERVER:$HUB/"
$SSH "$SERVER" SKILL_DIRS="'$SKILL_DIRS'" bash -s <<'EOF'
set -e
U=~/.config/systemd/user
cat > $U/claude-digest.service <<UNIT
[Unit]
Description=Digest Claude Code history into markdown for agents
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/claude-hub/digest.py
UNIT
cat > $U/claude-digest.timer <<UNIT
[Unit]
Description=Run claude-digest every 5 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now claude-digest.timer >/dev/null
for d in $SKILL_DIRS; do
  [ -d ~/"$d" ] && ln -sfn ~/claude-hub/skill/claude-context ~/"$d"/claude-context && echo "skill linked: ~/$d"
done
loginctl show-user "$USER" -p Linger | grep -q yes || echo "WARN: run 'sudo loginctl enable-linger $USER' so the timer runs while logged out"
EOF

# --- mac: launchd jobs ------------------------------------------------------
# rsync is launchd's direct program (not via bash) so a Full Disk Access grant
# on /usr/bin/rsync covers ~/Documents (macOS blocks launchd scripts there).
s() { for a in "$@"; do printf '    <string>%s</string>\n' "$a"; done; }

hist_ex=() ctx_ex=()
for p in $EXCLUDE_DIRS; do
  hist_ex+=(--exclude "$(printf %s "$p" | sed 's/[^A-Za-z0-9]/-/g')*")   # Claude's folder-name encoding
  case "$p" in "$CTX_ROOT"/*) ctx_ex+=(--exclude "/${p#"$CTX_ROOT"/}") ;; esac
done

plist() { # label, log name, rsync args...
  local label=$1 log=$2; shift 2
  local f=~/Library/LaunchAgents/$label.plist
  launchctl unload "$f" 2>/dev/null || true
  cat > "$f" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
$(s /usr/bin/rsync -az -e "$SSH" "$@")
  </array>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>/tmp/$log.log</string>
</dict></plist>
XML
  plutil -lint -s "$f"
  launchctl load "$f"
  echo "launchd: $label"
}

# History: no --delete, so the server keeps sessions Claude Code prunes locally.
plist claude-hub.history claude-hub-history ${hist_ex[@]+"${hist_ex[@]}"} "$HOME/.claude/projects/" "$SERVER:$HUB/data/"

# CLAUDE.md only, mirrored under the same absolute path (ctx/Users/<you>/...).
$SSH "$SERVER" "mkdir -p ~/$HUB/ctx$CTX_ROOT"
plist claude-hub.ctx claude-hub-ctx --prune-empty-dirs --delete --delete-excluded \
  --exclude node_modules --exclude .git --exclude Library --exclude vendor ${ctx_ex[@]+"${ctx_ex[@]}"} \
  --include '*/' --include CLAUDE.md --exclude '*' "$CTX_ROOT/" "$SERVER:$HUB/ctx$CTX_ROOT/"

echo "done. Logs: /tmp/claude-hub-history.log /tmp/claude-hub-ctx.log"
