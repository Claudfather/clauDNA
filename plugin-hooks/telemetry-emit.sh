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

# Strip "claudna:" prefix — emit bare slug per Claudosseum ingestion contract
SKILL_NAME="${SKILL_NAME#claudna:}"

# Guard the slug charset before it is interpolated into the hand-built JSON
# fallback below (the no-jq path). A real claudna skill slug is
# [A-Za-z0-9:_-]; anything else can't be one and would corrupt the JSON line
# (e.g. a stray backslash is an invalid escape). Drop the event rather than
# write malformed telemetry.
case "$SKILL_NAME" in
    ""|*[!A-Za-z0-9:_-]*) exit 0 ;;
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

# Session ID — use Claude's session ID if available, otherwise derive from PID
SESSION_ID="${CLAUDE_SESSION_ID:-$$}"

# Write JSONL line — Claudosseum ingestion contract:
# {"ts", "bot", "type", "source": "vitals", "data": {"skill_slug", "duration_ms", "success", "session_id"}}
if command -v jq &>/dev/null; then
    printf '%s\n' "$(jq -cn \
        --arg ts "$TIMESTAMP" \
        --arg bot "$BOT" \
        --arg type "skill_invocation" \
        --arg source "vitals" \
        --arg skill_slug "$SKILL_NAME" \
        --argjson duration_ms "null" \
        --argjson success "$SUCCESS" \
        --arg session_id "$SESSION_ID" \
        '{ts: $ts, bot: $bot, type: $type, source: $source, data: {skill_slug: $skill_slug, duration_ms: $duration_ms, success: $success, session_id: $session_id}}')" \
        >> "$TELEMETRY_PATH"
else
    # Manual JSON construction (no jq available)
    printf '{"ts":"%s","bot":"%s","type":"skill_invocation","source":"vitals","data":{"skill_slug":"%s","duration_ms":null,"success":%s,"session_id":"%s"}}\n' \
        "$TIMESTAMP" "$BOT" "$SKILL_NAME" "$SUCCESS" "$SESSION_ID" \
        >> "$TELEMETRY_PATH"
fi

# Opportunistic pruning: every ~100th write, prune entries older than 30 days.
# Use line count mod 100 as a cheap heuristic — avoids pruning on every write.
#
# Concurrency (#164): the old read→filter→mv-replace lost any event a
# concurrent hook appended between the read and the rename. Now: a mkdir
# lock ensures one pruner at a time (losers skip — the next 100th write
# prunes), and the pruner ROTATES the live file aside instead of replacing
# it. rename(2) is atomic: a writer holding an fd keeps appending to the
# rotated inode (read by the filter), and a writer opening after the
# rotation creates a fresh live file (untouched). Survivors append back to
# the live file. Residual caveat, documented: a writer that resolved the
# old path before the rotation but appends after the filter's read loses
# that one line — a microseconds window, down from the full prune duration.
# Pruning requires jq; without it the file simply grows (the old grep
# fallback silently kept everything anyway — now that behavior is explicit).
LINE_COUNT=$(wc -l < "$TELEMETRY_PATH" 2>/dev/null || echo "0")
LINE_COUNT=$(echo "$LINE_COUNT" | tr -d ' ')
if [ "$((LINE_COUNT % 100))" -eq "0" ] && [ "$LINE_COUNT" -gt "0" ] && command -v jq &>/dev/null; then
    CUTOFF=$(date -u -d "30 days ago" +"%Y-%m-%dT" 2>/dev/null || date -u -v-30d +"%Y-%m-%dT" 2>/dev/null || true)
    LOCKDIR="${TELEMETRY_PATH}.prune.lock"
    if [ -n "$CUTOFF" ] && mkdir "$LOCKDIR" 2>/dev/null; then
        trap 'rm -rf "$LOCKDIR"' EXIT
        ROTATED="${TELEMETRY_PATH}.pruning"
        if mv "$TELEMETRY_PATH" "$ROTATED" 2>/dev/null; then
            if jq -c "select(.ts >= \"$CUTOFF\")" "$ROTATED" >> "$TELEMETRY_PATH" 2>/dev/null; then
                rm -f "$ROTATED"
            else
                # Filter failed (malformed line?) — restore everything unpruned.
                cat "$ROTATED" >> "$TELEMETRY_PATH" 2>/dev/null || true
                rm -f "$ROTATED"
            fi
        fi
        rm -rf "$LOCKDIR"
        trap - EXIT
    fi
fi

exit 0
