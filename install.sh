#!/usr/bin/env bash
# Install the thanks-counter hook into ~/.claude (global, all projects).
# Safe to re-run: it replaces its own entry instead of adding a duplicate.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HOOK_DST="$CLAUDE_DIR/hooks/thanks_counter.py"
SETTINGS="$CLAUDE_DIR/settings.json"
SRC="$(cd "$(dirname "$0")" && pwd)/hooks/thanks_counter.py"

mkdir -p "$CLAUDE_DIR/hooks"
cp "$SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
fi

python3 - "$SETTINGS" "$HOOK_DST" <<'PY'
import json, os, sys

settings_path, hook_path = sys.argv[1], sys.argv[2]
settings = {}
if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)

command = "python3 " + json.dumps(hook_path)
groups = settings.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])

# Drop any earlier copy of this hook, then add it once.
for group in groups:
    group["hooks"] = [h for h in group.get("hooks", [])
                      if "thanks_counter.py" not in h.get("command", "")]
groups[:] = [g for g in groups if g.get("hooks")]
groups.append({"hooks": [{"type": "command", "command": command, "timeout": 5}]})

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY

echo "Installed hook: $HOOK_DST"
echo "Registered in:  $SETTINGS"
echo "Counter file:   $CLAUDE_DIR/thanks-count.json (created on first thanks)"
echo "Open a new Claude Code session for it to take effect."
