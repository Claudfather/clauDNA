#!/bin/bash
# PreCompact hook: auto-invoke /claudna:reflect before context compaction.
#
# On first compaction attempt per session, blocks compaction and instructs
# Claude to run /claudna:reflect first. On the second attempt (after reflect
# has run), allows compaction to proceed.
#
# Env vars:
#   CLAUDNA_PRECOMPACT_REFLECT  — "0" to disable (default: enabled)
#   CLAUDE_SESSION_ID           — session identifier (set by Claude Code)

set -euo pipefail

# Opt-out check: disabled when explicitly set to "0"
if [ "${CLAUDNA_PRECOMPACT_REFLECT:-1}" = "0" ]; then
    exit 0
fi

# Read hook input from stdin
EVENT=$(cat)

# Extract session ID for the marker file
SESSION_ID=""
if command -v jq &>/dev/null; then
    SESSION_ID=$(printf '%s' "$EVENT" | jq -r '.session_id // empty' 2>/dev/null || true)
fi
SESSION_ID="${SESSION_ID:-${CLAUDE_SESSION_ID:-$$}}"

MARKER_DIR="${TMPDIR:-/tmp}"
MARKER="${MARKER_DIR}/claudna-reflected-${SESSION_ID}"

if [ -f "$MARKER" ]; then
    # Reflect already ran this session — allow compaction
    rm -f "$MARKER"
    exit 0
fi

# First compaction attempt — block and request reflect
touch "$MARKER"
printf '{"decision":"block","reason":"Run /claudna:reflect to capture session learnings before compacting. Then run /compact again."}\n'
