#!/bin/bash
# SessionStart briefing hook for clauDNA (epic #165 P7, fork F3: on by default).
#
# Renders a short warm-start briefing from purely local + gh state — current
# branch/tree, the per-cwd handoff (<cwd>/.claude/session.md, written by
# /claudna:session), and open PRs — then an opener directive so the agent
# starts the session oriented instead of cold. Stdout lands in the agent's
# context (the SessionStart channel), never in the user's terminal.
#
# Invariants (enforced by tests/test_session_start_hook.py):
#   - ALWAYS exits 0 — a briefing failure must never break session start.
#   - CLAUDNA_SESSION_BRIEFING=0 disables it entirely (the opt-out, and the
#     documented headless mechanism: no reliable in-hook signal distinguishes
#     `claude -p`, so bots/CI set the env var — see SETUP_GUIDE).
#   - Hard time budget: every gh call is timeout-wrapped; git reads are local.
#   - Degrades silently: no git repo, no handoff, no gh, gh unauthed, gh slow,
#     or gh rate-limited → the affected section is simply omitted.
#
# Spike findings (recorded for #171): the SessionStart event fires on startup
# with plugin hooks wired exactly like this file; hook stdout is delivered
# into session context. Both verified by observing a live plugin environment.
# The `compact` trigger is deliberately NOT wired (decision rider: #176).

set -u

# Opt-out (default on, per fork F3)
if [ "${CLAUDNA_SESSION_BRIEFING:-1}" = "0" ]; then
    exit 0
fi

# Consume stdin (hook input JSON) without depending on it.
cat > /dev/null 2>&1 || true

CWD="${PWD}"

# --- Git state (local, fast). Not a repo → minimal briefing, still exit 0.
BRANCH=""
TREE=""
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    BRANCH=$(git branch --show-current 2>/dev/null || true)
    DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    if [ "${DIRTY:-0}" = "0" ]; then TREE="clean"; else TREE="dirty (${DIRTY} paths)"; fi
fi

# --- Handoff summary (the /claudna:session substrate)
HANDOFF="${CWD}/.claude/session.md"
HANDOFF_AGE=""
NEXT_STEPS=""
OPEN_QS=""
if [ -f "$HANDOFF" ]; then
    # File-mtime staleness, independent of per-bullet reaper TTLs.
    NOW=$(date +%s)
    # GNU-first: BSD stat's -f is filesystem-mode on GNU (prints junk, exits 1
    # only after polluting stdout), so probe -c first and hard-guard numerics.
    MTIME=$(stat -c %Y "$HANDOFF" 2>/dev/null || stat -f %m "$HANDOFF" 2>/dev/null || echo "$NOW")
    case "$MTIME" in ''|*[!0-9]*) MTIME="$NOW";; esac
    AGE_H=$(( (NOW - MTIME) / 3600 ))
    if [ "$AGE_H" -lt 24 ]; then HANDOFF_AGE="${AGE_H}h ago"
    else HANDOFF_AGE="$(( AGE_H / 24 ))d ago (stale — treat next steps as hypotheses)"; fi
    # First 3 bullets under "Next Steps" / "Open Questions" (tolerant of ## or ###).
    NEXT_STEPS=$(awk '/^#+ *Next Steps/{f=1; next} /^#+ /{f=0} f && /^- /{print; c++} c==3{exit}' "$HANDOFF" 2>/dev/null || true)
    OPEN_QS=$(awk '/^#+ *Open Questions/{f=1; next} /^#+ /{f=0} f && /^- /{print; c++} c==2{exit}' "$HANDOFF" 2>/dev/null || true)
fi

# --- Open PRs (network — timeout-wrapped, silently skipped on any failure)
PRS=""
REVIEW_REQ=""
if [ -n "$BRANCH" ] && command -v gh > /dev/null 2>&1; then
    # timeout(1) is not a stock macOS binary — wrap only when present.
    TO=""
    command -v timeout > /dev/null 2>&1 && TO="timeout 3"
    # Parallel: two network reads must not serialize into a session-start stall.
    PRS_F=$(mktemp); REVQ_F=$(mktemp)
    ( $TO gh pr list --author @me --limit 3 --json number,title,state \
        --template '{{range .}}#{{.number}} {{.title}} ({{.state}}){{"\n"}}{{end}}' > "$PRS_F" 2>/dev/null || true ) &
    ( $TO gh pr list --search "review-requested:@me" --limit 3 --json number,title \
        --template '{{range .}}#{{.number}} {{.title}}{{"\n"}}{{end}}' > "$REVQ_F" 2>/dev/null || true ) &
    wait
    PRS=$(cat "$PRS_F" 2>/dev/null || true)
    REVIEW_REQ=$(cat "$REVQ_F" 2>/dev/null || true)
    rm -f "$PRS_F" "$REVQ_F"
fi

# --- Emit. Nothing to say → say nothing.
if [ -z "$BRANCH" ] && [ -z "$NEXT_STEPS" ] && [ -z "$OPEN_QS" ] && [ -z "$PRS" ]; then
    exit 0
fi

echo "<claudna-session-briefing>"
echo "Repo state: branch ${BRANCH:-<none>} · tree ${TREE:-n/a}"
if [ -n "$HANDOFF_AGE" ]; then
    echo "Last handoff: ${HANDOFF_AGE} (${HANDOFF})"
    [ -n "$NEXT_STEPS" ] && { echo "Next steps from the handoff:"; echo "$NEXT_STEPS"; }
    [ -n "$OPEN_QS" ] && { echo "Open questions:"; echo "$OPEN_QS"; }
else
    echo "No handoff for this directory — /claudna:session handoff writes one at session end."
fi
[ -n "$PRS" ] && { echo "Open PRs (yours):"; echo "$PRS"; }
[ -n "$REVIEW_REQ" ] && { echo "PRs awaiting your review:"; echo "$REVIEW_REQ"; }
echo "</claudna-session-briefing>"
echo ""
echo "Briefing directive: if the user's first message doesn't set its own direction, open with 1-2 sentences synthesizing the state above (never paste the raw briefing) and offer a concrete either/or — picking up the top next step, or pivoting. If a next step references a file, verify it still exists before recommending it. For the full resume ceremony, /claudna:session resume."

exit 0
