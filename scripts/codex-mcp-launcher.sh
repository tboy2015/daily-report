#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER_PATH="$SCRIPT_DIR/mcp-server.py"

if command -v uv >/dev/null 2>&1; then
  exec uv run "$SERVER_PATH"
fi

if [ -x /opt/homebrew/bin/uv ]; then
  exec /opt/homebrew/bin/uv run "$SERVER_PATH"
fi

if [ -x /usr/local/bin/uv ]; then
  exec /usr/local/bin/uv run "$SERVER_PATH"
fi

echo "daily-report: uv executable not found; install uv and restart Codex" >&2
exit 127
