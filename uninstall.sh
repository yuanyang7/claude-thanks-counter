#!/usr/bin/env bash
# Remove the thanks-counter hook. Keeps thanks-count.json so your total survives.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"

if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
  python3 - "$SETTINGS" <<'PY'
import json, sys

path = sys.argv[1]
with open(path) as f:
    settings = json.load(f)
hooks = settings.get("hooks", {})
groups = hooks.get("UserPromptSubmit", [])
for group in groups:
    group["hooks"] = [h for h in group.get("hooks", [])
                      if "thanks_counter.py" not in h.get("command", "")]
groups[:] = [g for g in groups if g.get("hooks")]
if not groups:
    hooks.pop("UserPromptSubmit", None)
if not hooks:
    settings.pop("hooks", None)
with open(path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY
fi

rm -f "$CLAUDE_DIR/hooks/thanks_counter.py"
echo "Removed the hook. Your count and notes are still in $CLAUDE_DIR/."
