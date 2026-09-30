#!/usr/bin/env bash
set -eo pipefail

# PreToolUse permissions hook for Claude Code
#
# Auto-approves Bash commands where every sub-command matches a pattern
# in permissions.allow. Handles compound commands (&&, ||, |, ;, &) by
# splitting and validating each part independently.
#
# Security note: This hook bypasses Claude Code's undocumented "write
# safety" check for file-modifying commands (mkdir, touch, cp, mv).
# Commands in the allow list will auto-approve without the secondary
# prompt. If you don't want a command auto-approved, remove it from
# permissions.allow.
#
# Behavior:
#   - Only processes Bash tool calls; other tools pass through
#   - Loads patterns from ~/.claude/settings.json, .claude/settings.json,
#     and .claude/settings.local.json
#   - Falls through (no output) for unrecognized or unparseable commands
#   - Never returns "deny" — only "allow" or silent pass-through
#   - Debug log: ${XDG_STATE_HOME:-~/.local/state}/claudna/permissions.log,
#     readable by the user alone
#
# Compound-command splitting scope:
#   Handled (split + each part validated independently):
#     &&   ||   |   ;   &   (lone & = background operator, splits like ;)
#
#   `&` stays literal inside a redirection (2>&1, >&, <&, &>) — there it is
#   fd-duplication, not a control operator, so it is not a split point.
#
#   NOT handled (detected early and falls through — user gets a permission prompt):
#     $( )       command substitution
#     ` `        backtick command substitution
#     <( ) >( )  process substitution
#     <<  <<<    here-docs and here-strings
#     { ; }      brace groups (not detected — falls through via match failure)
#     nested quoting edge cases beyond basic single/double quote tracking

# The log holds whole command lines: it lives in the user's own state directory,
# and every file the hook creates is readable by the user alone.
STATE_HOME="${XDG_STATE_HOME:-${HOME:+$HOME/.local/state}}"
LOG_DIR="${STATE_HOME:+$STATE_HOME/claudna}"
LOG="$LOG_DIR/permissions.log"
MAX_LOG_SIZE=1048576  # 1MB
umask 077

# ─── Helpers ──────────────────────────────────────────────────────────

log() {
    [[ -n "$LOG_DIR" ]] || return 0
    [[ -d "$LOG_DIR" ]] || mkdir -p -m 700 "$LOG_DIR" 2>/dev/null || return 0
    if [[ -f "$LOG" ]]; then
        local size
        size=$(wc -c < "$LOG" 2>/dev/null) || size=0
        if (( ${size:-0} > MAX_LOG_SIZE )); then
            mv "$LOG" "$LOG.old" 2>/dev/null || true
        fi
    fi
    printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" >> "$LOG" 2>/dev/null || true
}

approve() {
    local reason="${1:-all sub-commands match allow patterns}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","reason":"%s"}}\n' "$reason"
    log "ALLOW: $COMMAND ($reason)"
    exit 0
}

# A hook "deny" overrides a settings allow rule and a skill's allowed-tools, so it
# is the one way to close a leak that rides inside an already-granted command.
deny() {
    local reason="${1:-blocked by policy}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
    log "DENY: $COMMAND ($reason)"
    exit 0
}

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Require jq ───────────────────────────────────────────────────────

command -v jq &>/dev/null || exit 0

# ─── Parse input + load patterns (single jq call) ────────────────────

INPUT=$(cat)

JQ_RESULT="$(
  { printf '%s\n' "$INPUT"
    cat "$HOME/.claude/settings.json" 2>/dev/null || echo '{}'
    cat ".claude/settings.json" 2>/dev/null || echo '{}'
    cat ".claude/settings.local.json" 2>/dev/null || echo '{}'
  } | jq -s -r '
    .[0] as $input |
    ($input.tool_name // "") as $tool |
    ($input.tool_input.command // "") as $cmd |
    if $tool != "Bash" or $cmd == "" then "exit 0"
    else
      (.[1].permissions.allow? // []) as $user |
      ((.[2].permissions.allow? // []) + (.[3].permissions.allow? // [])) as $proj |
      ([$user[] | select(. == "Bash")] | length > 0) as $has_bare |
      ([$user[] | select(startswith("Bash(")) |
        ltrimstr("Bash(") | rtrimstr(")")]) as $user_specs |
      ([$proj[] | select(startswith("Bash(")) |
        ltrimstr("Bash(") | rtrimstr(")") |
        select((contains("*") or contains("?") or contains("[")) | not)]) as $proj_specs |
      (($user_specs + $proj_specs) | unique) as $specs |
      "COMMAND=" + ($cmd | @sh) +
      "\nHAS_BARE=" + (if $has_bare then "true" else "false" end) +
      "\nSPECS=(" + ([$specs[] | @sh] | join(" ")) + ")"
    end
  ' 2>/dev/null
)" || exit 0

eval "$JQ_RESULT"

# ─── gh read-guard → deny before any approve ──────────────────────────
# A pre-approved `gh` READ verb can move an environment-resident token off the box,
# or reach a host other than github.com, through its own flags: `--jq env.X` prints
# a secret, `-R host/owner/repo` and a URL positional send the request (and any
# --search text) to a named host, `--web` opens one. This denies exactly those
# shapes and nothing else — the fleet's `--json`/`--jq '.field'` reads pass through.
# It runs before the bare-Bash and allow-pattern approvals, because a hook "deny"
# is the only decision that overrides an allow grant. Zero-fork prefilter: python3
# is spawned only for a command that names `gh` alongside one of the trigger flags.
case "$COMMAND" in
    *gh*)
        case "$COMMAND" in
            *--jq*|*--template*|*--repo*|*--web*|*" -q"*|*" -t"*|*" -R"*|*" -w"*|*"://"*)
                if command -v python3 &>/dev/null; then
                    # errexit-safe: the decider exits 10 to deny, and an
                    # assignment that inherits that would end the hook here.
                    if GH_GUARD_REASON="$(python3 "$HOOK_DIR/gh-guard-decide.py" "$COMMAND" 2>/dev/null)"; then
                        : # exit 0 → allow this shape; fall through to normal matching
                    elif [[ $? -eq 10 ]]; then
                        deny "$GH_GUARD_REASON"
                    fi
                else
                    log "PASS: $COMMAND (gh guard skipped, no python3)"
                fi
                ;;
        esac
        ;;
esac

# ─── Bare "Bash" in allow list → approve all ──────────────────────────

if $HAS_BARE; then
    approve "bare Bash in allow list"
fi

# ─── No patterns loaded → fall through ────────────────────────────────

if [[ ${#SPECS[@]} -eq 0 ]]; then
    log "PASS: $COMMAND (no allow patterns)"
    exit 0
fi

# ─── Detect unparseable constructs → fall through ─────────────────────

case "$COMMAND" in
    *'<<'*|*'$('*|*'`'*|*'<('*|*'>('*)
        log "PASS: $COMMAND (unparseable construct)"
        exit 0
        ;;
esac

# ─── Split command on shell operators (quote-aware) ───────────────────

split_commands() {
    local cmd="$1"
    local len=${#cmd}
    local i=0 char
    local sq=false dq=false
    local current=""

    while (( i < len )); do
        char="${cmd:i:1}"

        if $sq; then
            [[ "$char" == "'" ]] && sq=false
            current+="$char"
        elif $dq; then
            if [[ "$char" == "\\" ]] && (( i + 1 < len )); then
                current+="$char${cmd:i+1:1}"
                i=$((i + 2)); continue
            fi
            [[ "$char" == '"' ]] && dq=false
            current+="$char"
        else
            case "$char" in
                "'") sq=true; current+="$char" ;;
                '"') dq=true; current+="$char" ;;
                "\\")
                    if (( i + 1 < len )); then
                        current+="$char${cmd:i+1:1}"
                        i=$((i + 2)); continue
                    fi
                    current+="$char"
                    ;;
                "&")
                    # && → logical-AND separator (both sides run in sequence)
                    if [[ "${cmd:i+1:1}" == "&" ]]; then
                        printf '%s\n' "$current"
                        current=""
                        i=$((i + 2)); continue
                    fi
                    # Keep & literal inside a redirection — 2>&1 / >& / <&
                    # (preceded by > or <), and &> / &>> (followed by >).
                    if { (( i > 0 )) && [[ "${cmd:i-1:1}" == ">" || "${cmd:i-1:1}" == "<" ]]; } \
                       || [[ "${cmd:i+1:1}" == ">" ]]; then
                        current+="$char"
                    else
                        # Lone & is the background control operator: the command
                        # before it runs AND execution continues to what follows,
                        # so it separates exactly like ; — each side must match
                        # on its own or the whole command prompts.
                        printf '%s\n' "$current"
                        current=""
                    fi
                    ;;
                "|")
                    if [[ "${cmd:i+1:1}" == "|" ]]; then
                        printf '%s\n' "$current"
                        current=""
                        i=$((i + 2)); continue
                    fi
                    printf '%s\n' "$current"
                    current=""
                    ;;
                ";")
                    printf '%s\n' "$current"
                    current=""
                    ;;
                *) current+="$char" ;;
            esac
        fi
        i=$((i + 1))
    done

    if $sq || $dq; then
        return 1
    fi

    [[ -n "$current" ]] && printf '%s\n' "$current"
    return 0
}

# ─── Pattern matching ─────────────────────────────────────────────────

matches_any() {
    local cmd="$1"
    shift
    local spec
    for spec in "$@"; do
        # shellcheck disable=SC2254  # glob matching is intentional
        case "$cmd" in
            $spec) return 0 ;;
        esac
    done
    return 1
}

# ─── Write-redirection guard ──────────────────────────────────────────
# A prefix rule like `Bash(git *)` glob-matches the whole sub-command, so
# `git log > ~/.bashrc` matches `git *` and would auto-approve a write to a
# path the rule never meant to cover. A redirection is not a split point, so
# it rides inside the sub-command. Force a prompt on any output redirection to
# a file, even on a prefix match. fd-duplications (2>&1, >&2) and the std
# devices are not writable files a rule needs to cover, and stay auto-approvable.
has_write_redirection() {
    local s
    s="$(printf '%s' "$1" | sed -E '
        s/[0-9]*[<>]&[0-9-]+//g
        s/[0-9]*>>?[[:space:]]*\/dev\/(null|stdout|stderr)\>//g
    ')"
    [[ "$s" == *'>'* ]]
}

# ─── Main logic ───────────────────────────────────────────────────────

SPLIT_OUTPUT=$(split_commands "$COMMAND") || {
    log "PASS: $COMMAND (unmatched quotes)"
    exit 0
}

SUBCMDS=()
while IFS= read -r line; do
    read -r trimmed <<< "$line"
    [[ -n "$trimmed" ]] && SUBCMDS+=("$trimmed")
done <<< "$SPLIT_OUTPUT"

if [[ ${#SUBCMDS[@]} -eq 0 ]]; then
    log "PASS: $COMMAND (empty after split)"
    exit 0
fi

for sub in "${SUBCMDS[@]}"; do
    if has_write_redirection "$sub"; then
        log "PASS: $COMMAND (write redirection, prompt kept: $sub)"
        exit 0
    fi
    if ! matches_any "$sub" "${SPECS[@]}"; then
        log "PASS: $COMMAND (no match for: $sub)"
        exit 0
    fi
done

if [[ ${#SUBCMDS[@]} -eq 1 ]]; then
    approve "matches allow pattern"
else
    approve "all ${#SUBCMDS[@]} sub-commands match allow patterns"
fi
