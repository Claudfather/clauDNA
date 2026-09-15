#!/bin/bash
# Auto-format hook for Claude Code
# Runs after Write/Edit operations to format code.
#
# Deliberately not `set -e`. The formatters below exit nonzero for legitimate
# reasons — `ruff check --fix` does it whenever a violation remains unfixable —
# so under `-e` the ordinary "file still has lint" case would exit 1 and collide
# with the meaning this hook assigns to exit 1 below. Dropping `-e` is what keeps
# that exit code single-meaninged; it also stops one failing formatter from
# skipping the rest.
#
# `pipefail` is omitted rather than forgotten: every pipeline here sits inside a
# command substitution whose status nothing reads, so it is measurably inert, and
# `set -u` alone matches session-start.sh, the other degrade-don't-abort hook.
set -u

# Read the hook event from stdin
EVENT=$(cat)

# Nothing on stdin is not a failure — there is simply no event to act on.
if [ -z "$EVENT" ]; then
    exit 0
fi

# Extract the target path from the event.
#
# The payload's whitespace is not part of any published contract, so parse it as
# JSON where possible. The two rungs chain rather than branch on `jq` presence: a
# fallback reachable only on a host without `jq` is never exercised on a host
# that has it.
#
# `jq` is the FIRST rung even though it is the expensive one — ~47ms of startup
# on this host against ~0.1ms for a bash regex, on every Write and Edit. It is
# first because a text pattern takes the first `file_path` in the payload, which
# is the right one only while `tool_input` happens to precede `tool_response`.
# That is one more uncontracted property of the same producer, and trading
# whitespace-order for key-order is not a fix. The text rung keeps that
# limitation knowingly: it is the degraded path for a host with no `jq`.
FILE_PATH=""
if command -v jq &>/dev/null; then
    FILE_PATH=$(printf '%s' "$EVENT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
if [ -z "$FILE_PATH" ]; then
    FILE_PATH=$(printf '%s' "$EVENT" \
        | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | head -1 \
        | cut -d'"' -f4)
fi

# A non-empty payload that yields no path is a PARSE failure, not an event
# without a target: this hook matches Write|Edit only, and both always carry the
# file they acted on. The matcher does not reach NotebookEdit, whose payload
# carries `notebook_path` instead and would otherwise be a legitimate no-path
# event — measured, with a Write through the same matcher as a positive control.
#
# Exiting 0 here is precisely what let a whitespace-fragile parse switch the hook
# off with no error, no log and no exit code. Exit 1 surfaces the message without
# blocking the tool call; exit 2 would feed the model, which is not wanted for a
# formatter that has already missed its chance to run.
if [ -z "$FILE_PATH" ]; then
    printf 'auto-format: could not resolve tool_input.file_path from the hook payload; nothing formatted\n' >&2
    exit 1
fi

# Format based on file extension
case "$FILE_PATH" in
    *.py)
        # Python: use ruff if available
        if command -v ruff &> /dev/null; then
            ruff format "$FILE_PATH" 2>/dev/null
            ruff check --fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.js|*.jsx|*.ts|*.tsx|*.json|*.md)
        # JavaScript/TypeScript/JSON/Markdown: use prettier if available
        if command -v prettier &> /dev/null; then
            prettier --write "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.sql)
        # SQL: use sqlfluff if available
        if command -v sqlfluff &> /dev/null; then
            sqlfluff fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
esac

exit 0
