#!/bin/bash
# Telemetry emission hook for clauDNA skill invocations
# PostToolUse hook — fires after Skill tool calls.
#
# Emits skill_invocation events as JSONL to a local file.
# No phone home — the fleet observability system can optionally push to Claudosseum.
#
# Env vars:
#   CLAUDNA_TELEMETRY       — "1" to enable, "0" or unset to disable
#   CLAUDNA_TELEMETRY_PATH  — output file (default: ~/.claude/telemetry/skill-events.jsonl)
#   BOT_NAME                — bot identity (default: "interactive")

set -euo pipefail

# Opt-in check: exit immediately if telemetry is not explicitly enabled
if [ "${CLAUDNA_TELEMETRY:-0}" != "1" ]; then
    exit 0
fi

# Read hook input from stdin
EVENT=$(cat)

# Extract skill name from the hook input.
# The Skill tool receives a "skill" parameter — try jq first, fall back to grep.
SKILL_NAME=""
if command -v jq &>/dev/null; then
    # tool_input.skill holds the skill name passed to the Skill tool
    SKILL_NAME=$(printf '%s' "$EVENT" | jq -r '.tool_input.skill // .tool_input.name // empty' 2>/dev/null || true)
else
    # grep fallback: extract "skill":"<value>" from JSON
    SKILL_NAME=$(printf '%s' "$EVENT" | grep -o '"skill":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
    if [ -z "$SKILL_NAME" ]; then
        SKILL_NAME=$(printf '%s' "$EVENT" | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
    fi
fi

# Only emit for claudna skills (claudna:* pattern)
case "$SKILL_NAME" in
    claudna:*) ;;
    *) exit 0 ;;
esac

# Determine output path
TELEMETRY_PATH="${CLAUDNA_TELEMETRY_PATH:-${HOME}/.claude/telemetry/skill-events.jsonl}"
TELEMETRY_DIR=$(dirname "$TELEMETRY_PATH")

# Create directory if needed
mkdir -p "$TELEMETRY_DIR"

# Build event fields
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BOT="${BOT_NAME:-interactive}"

# Check for error indicators in tool output (simple heuristic)
SUCCESS="true"
if command -v jq &>/dev/null; then
    TOOL_OUTPUT=$(printf '%s' "$EVENT" | jq -r '.tool_output // empty' 2>/dev/null || true)
else
    TOOL_OUTPUT=$(printf '%s' "$EVENT" | grep -o '"tool_output":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
fi
if [ -n "$TOOL_OUTPUT" ]; then
    case "$TOOL_OUTPUT" in
        *[Ee]rror*|*[Ff]ailed*|*[Ee]xception*|*ERROR*|*FAILED*)
            SUCCESS="false"
            ;;
    esac
fi

# Write JSONL line — use printf to avoid issues with special characters
if command -v jq &>/dev/null; then
    printf '%s\n' "$(jq -cn \
        --arg event "skill_invocation" \
        --arg skill "$SKILL_NAME" \
        --arg ts "$TIMESTAMP" \
        --arg bot "$BOT" \
        --argjson duration_ms "null" \
        --argjson success "$SUCCESS" \
        '{event: $event, skill: $skill, ts: $ts, bot: $bot, duration_ms: $duration_ms, success: $success}')" \
        >> "$TELEMETRY_PATH"
else
    # Manual JSON construction (no jq available)
    printf '{"event":"skill_invocation","skill":"%s","ts":"%s","bot":"%s","duration_ms":null,"success":%s}\n' \
        "$SKILL_NAME" "$TIMESTAMP" "$BOT" "$SUCCESS" \
        >> "$TELEMETRY_PATH"
fi

# Opportunistic pruning: every ~100th write, prune entries older than 30 days.
# Use line count mod 100 as a cheap heuristic — avoids pruning on every write.
LINE_COUNT=$(wc -l < "$TELEMETRY_PATH" 2>/dev/null || echo "0")
LINE_COUNT=$(echo "$LINE_COUNT" | tr -d ' ')
if [ "$((LINE_COUNT % 100))" -eq "0" ] && [ "$LINE_COUNT" -gt "0" ]; then
    CUTOFF=$(date -u -d "30 days ago" +"%Y-%m-%dT" 2>/dev/null || date -u -v-30d +"%Y-%m-%dT" 2>/dev/null || true)
    if [ -n "$CUTOFF" ]; then
        TMPFILE=$(mktemp "${TELEMETRY_DIR}/prune.XXXXXX")
        if command -v jq &>/dev/null; then
            jq -c "select(.ts >= \"$CUTOFF\")" "$TELEMETRY_PATH" > "$TMPFILE" 2>/dev/null || cp "$TELEMETRY_PATH" "$TMPFILE"
        else
            # grep fallback: keep lines where the timestamp is >= cutoff
            # This is approximate but safe — worst case we keep a few extra lines
            grep -v "\"ts\":\"[0-9T:-]*\"" "$TELEMETRY_PATH" > "$TMPFILE" 2>/dev/null || true
            grep "\"ts\":\"${CUTOFF%T}" "$TELEMETRY_PATH" >> "$TMPFILE" 2>/dev/null || true
            # If fallback is unreliable, just keep everything
            if [ ! -s "$TMPFILE" ]; then
                cp "$TELEMETRY_PATH" "$TMPFILE"
            fi
        fi
        mv "$TMPFILE" "$TELEMETRY_PATH"
    fi
fi

exit 0
