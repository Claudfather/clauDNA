#!/bin/bash
# PreCompact hook: prompt for /claudna:capture before context compaction —
# UNLESS the engine now owns that prompt (defer gate below).
#
# On the first compaction attempt per session, blocks compaction and instructs
# Claude to run /claudna:capture first (a bare capture distills the session).
# On the second attempt (after capture has run), allows compaction to proceed.
#
# Capture-prompt defer:
# Claudron's engine also ships a PreCompact prompt. Exactly one participant may
# hold R-capture-prompt per session (Claudron docs/CLI_CONTRACT.md §Session-loop
# protocol). When the engine's PreCompact hook is registered AND the engine is
# new enough that it ALWAYS prompts (its transitional glob shim is gone), this
# front-end stands aside and lets the engine's front-end-neutral prompt cover
# the session — that prompt still routes the agent to /claudna:capture. The
# defer is version-gated and FAIL-SAFE; see the gate below.
#
# Filename, the CLAUDNA_PRECOMPACT_REFLECT opt-out, and the marker keep their
# historical names for now; the hook restructure (SessionEnd + stacking) is #203.
#
# Env vars:
#   CLAUDNA_PRECOMPACT_REFLECT  — "0" to disable (default: enabled)
#   CLAUDE_SESSION_ID           — session identifier (set by Claude Code)

set -euo pipefail

# Opt-out check: disabled when explicitly set to "0"
if [ "${CLAUDNA_PRECOMPACT_REFLECT:-1}" = "0" ]; then
    exit 0
fi

# ─── Capture-prompt defer gate ─────────────────────────────────────────
#
# SHIM_REMOVAL_RELEASE — the Claudron engine release that removed the
# transitional PreCompact glob shim (Claudron #85 / PR #90). Its significance:
#
#   • BEFORE this release, the engine's PreCompact hook YIELDS to a detected
#     clauDNA plugin (the glob shim in Claudron hooks.py). If this front-end
#     ALSO defers there, BOTH sides yield and *nobody* prompts — durable
#     capture stops, silently. That is the ordering hazard, and the whole
#     reason this defer is version-gated.
#   • AT/AFTER this release, the engine ALWAYS prompts wherever its hook is
#     installed, in text that names no front-end. Only then is deferring safe.
#
# We therefore defer ONLY when the probed engine_version >= this release.
#
# !! VERIFY / FINALIZE THIS VALUE WHEN THE CLAUDRON SHIM-REMOVAL RELEASE CUTS !!
# As of this writing the removal sits in Claudron's CHANGELOG `## Unreleased`,
# above the released v0.3.0; Claudron's roadmap names 0.4.0 as the next release,
# so 0.4.0 is the planned removal release. This constant MUST be >= the version
# that actually ships the shim removal, and MUST NEVER be set lower: erring HIGH
# costs at most a bounded double-prompt (the engine and this hook both prompt)
# until it is corrected; erring LOW re-opens the silent no-prompt hazard above.
SHIM_REMOVAL_RELEASE="0.4.0"

# version_ge HAVE FLOOR — return 0 iff HAVE >= FLOOR, comparing only the leading
# numeric MAJOR.MINOR.PATCH core (so "0.4.0-dev.3+g1a2b" compares as 0.4.0 and
# "0.0.0-dev" as 0.0.0). ANY parse ambiguity returns 1 ("below the floor") — the
# fail-safe direction: an unreadable version must never license a defer. Splits
# with `set --` under a local IFS (no here-string, so no temp-file dependency).
version_ge() {
    local have="$1" floor="$2"
    have="${have%%[!0-9.]*}"          # drop from the first non-[0-9.] char on
    local hj hn hp fj fn fp part
    local IFS=.
    # shellcheck disable=SC2086  # deliberate IFS='.' word-split on the version
    set -- $have;  hj="${1:-0}"; hn="${2:-0}"; hp="${3:-0}"
    # shellcheck disable=SC2086
    set -- $floor; fj="${1:-0}"; fn="${2:-0}"; fp="${3:-0}"
    for part in "$hj" "$hn" "$hp"; do
        [[ "$part" =~ ^[0-9]+$ ]] || return 1   # non-numeric core → below floor
    done
    (( 10#$hj > 10#$fj )) && return 0
    (( 10#$hj < 10#$fj )) && return 1
    (( 10#$hn > 10#$fn )) && return 0
    (( 10#$hn < 10#$fn )) && return 1
    (( 10#$hp >= 10#$fp ))
}

# engine_precompact_registered — return 0 iff a Claudron PreCompact hook is
# registered in the host's hook-settings files: a hook command ending in
# `hook pre-compact`, the normative identity Claudron's CLI_CONTRACT.md
# §Session-loop protocol pins (the suffix `merge_settings` keys on). Reads
# exactly the three Claude Code settings files, the `pretooluse-permissions.sh`
# read pattern. The whole match runs inside jq (no bash loop, no here-string):
# `-e` makes jq exit 0 only when some PreCompact command matches. jq is
# required; without it we cannot confirm registration → return 1 (do not defer —
# the fail-safe direction). clauDNA's own PreCompact hook lives in the plugin
# manifest, not these files, and its command does not end in `hook pre-compact`,
# so it can never be mistaken for the engine's.
engine_precompact_registered() {
    command -v jq &>/dev/null || return 1
    { cat "$HOME/.claude/settings.json"  2>/dev/null || echo '{}'
      cat ".claude/settings.json"        2>/dev/null || echo '{}'
      cat ".claude/settings.local.json"  2>/dev/null || echo '{}'
    } | jq -s -e '
        any(
          .[] | .hooks?.PreCompact? // [] | .[]? | .hooks? // [] | .[]? |
          .command? // empty;
          test("(^|\\s)hook\\s+pre-compact\\s*$")
        )
    ' >/dev/null 2>&1
}

# probe_engine_version — print the engine version via the sanctioned capability
# probe (`claudron status --json` → data.engine_version), or nothing. Bounded so
# a slow/hung engine cannot stall compaction; always exits 0 (an absent version
# is a valid answer and drives the fail-safe "do not defer" branch).
probe_engine_version() {
    command -v claudron &>/dev/null || return 0
    command -v jq &>/dev/null || return 0
    local t=""
    if command -v timeout &>/dev/null; then t="timeout 3"
    elif command -v gtimeout &>/dev/null; then t="gtimeout 3"
    fi
    local out
    out="$($t claudron status --json 2>/dev/null)" || return 0
    printf '%s' "$out" | jq -r '.data.engine_version // empty' 2>/dev/null || return 0
}

# Read hook input from stdin (drains the pipe before any early exit).
EVENT=$(cat)

# Defer decision — BOTH conditions must hold, or this hook prompts:
#   (1) the engine's PreCompact hook is registered — it WILL prompt; and
#   (2) engine_version >= SHIM_REMOVAL_RELEASE — its prompt is front-end-neutral
#       and it no longer yields the role back to us.
# A missing/old/unparseable version, or no registered engine hook → we prompt.
# The unsafe outcome (both sides yield, nobody prompts) is impossible by
# construction: we step aside only after confirming the engine both prompts and
# will not yield.
if engine_precompact_registered; then
    ENGINE_VERSION="$(probe_engine_version)" || true
    if [ -n "$ENGINE_VERSION" ] && version_ge "$ENGINE_VERSION" "$SHIM_REMOVAL_RELEASE"; then
        # Engine owns R-capture-prompt this session — allow compaction without
        # blocking; the engine's neutral prompt still routes to /claudna:capture.
        exit 0
    fi
fi

# ── clauDNA owns the prompt (no engine hook, or engine too old to trust) ──

# Extract session ID for the marker file
SESSION_ID=""
if command -v jq &>/dev/null; then
    SESSION_ID=$(printf '%s' "$EVENT" | jq -r '.session_id // empty' 2>/dev/null || true)
fi
SESSION_ID="${SESSION_ID:-${CLAUDE_SESSION_ID:-}}"

# Validate before the id becomes part of a filesystem path below. A value
# bearing '/' (or other path metacharacters) could point the marker outside
# the marker dir. Claude Code generates a UUID here, so a value outside this
# charset is malformed — treat it like a missing id and fail-open.
case "$SESSION_ID" in
    *[!A-Za-z0-9._-]*) SESSION_ID="" ;;
esac

# No stable session ID available — fail-open to avoid infinite block loop
# ($$ changes per subprocess invocation, so marker files would never match)
if [ -z "$SESSION_ID" ]; then
    exit 0
fi

MARKER_DIR="${TMPDIR:-/tmp}"
MARKER="${MARKER_DIR}/claudna-reflected-${SESSION_ID}"

if [ -f "$MARKER" ]; then
    # Capture already ran this session — allow compaction
    rm -f "$MARKER"
    exit 0
fi

# First compaction attempt — block and request capture
touch "$MARKER"
printf '{"decision":"block","reason":"Run /claudna:capture to distill session learnings before compacting. Then run /compact again."}\n'
