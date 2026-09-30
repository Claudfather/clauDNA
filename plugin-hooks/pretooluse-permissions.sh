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
#   - Returns "deny" only for the gh read-guard shapes (a granted gh read that
#     would read the environment or reach a host other than github.com); every
#     other command is "allow" or silent pass-through
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
#     a gh sub-command in which an expansion can form or change an option
#                word ($'..', ${X-..}, {a,b}, --j${Z}q); see gh_option_expansion

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
# A verb that takes a repository (gh repo view|clone|fork ...) is read when a word
# after it has two slashes: HOST/OWNER/REPO names its host like -R does.
# The shell removes quotes and backslashes before gh runs, so a flag spelled --j"q" or
# -\q is the flag. The prefilter reads the command without them; the decider gets the
# real text. One expansion, no fork.
NL=$'\n'
NOQ=${COMMAND//\\"$NL"/}   # bash joins a backslash-newline before it splits words
NOQ=${NOQ//[\"\'\\]/}
case "$NOQ" in
    *gh*)
        case "$NOQ" in
            *--jq*|*--template*|*--repo*|*--web*|*--hostname*|*[[:space:]]-q*|*[[:space:]]-t*|*[[:space:]]-R*|*[[:space:]]-w*|*[[:space:]]-[[:alnum:]]*[qtRw]*|*"://"*|*@*:*|*gh[[:space:]]*repo[[:space:]]*/*/*|*gh[[:space:]]*label[[:space:]]*/*/*|*gh[[:space:]]*ext*/*/*|*gh[[:space:]]*skill*/*/*)
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

# ─── An expansion that can form a gh option → fall through ────────────
# The shell expands a word before gh reads it: `$'--jq'`, `${X---jq}`,
# `--j${Z}q` and `{--jq,x}` all reach gh as --jq, while the gh guard above reads
# the unexpanded text. Approving such a command here would put it past Claude
# Code's own permission check, so a gh sub-command is not approved when an
# expansion in it can form or change an option word:
#   - ANSI-C or locale quoting, $'...' or $"...";
#   - a ${...} whose operator puts text from the command into the word
#     (${X-..}, ${X:=..}, ${X+..}, ${X/../..}, ${X@..}); a strip, a substring or
#     an index only reads the variable, like $X;
#   - a brace expansion, {a,b} or {a..b} (gh's own {owner}/{repo} is plain text);
#   - a parameter expansion or an unquoted glob inside a word that starts with a
#     dash once every expansion in it is taken as empty (--j${Z}q, $X--jq, -?),
#     or an unquoted glob that starts a word.
# A word that is only a parameter, $N or "$N", stays approved: its value comes
# from the environment, not from the command text (an assignment is a separate
# sub-command, and no allow pattern matches one).
# gh is the command word: first, after any VAR=value prefixes, or after a wrapper
# the gh guard also looks through. An echo that mentions gh is not a gh command.
is_gh_command() {
    local -a w
    local k=0 x
    read -ra w <<< "${1//[\"\'\\]/}"
    while [[ "${w[k]:-}" == [A-Za-z_]*=* ]]; do k=$((k + 1)); done
    case "${w[k]:-}" in
        gh|*/gh) return 0 ;;
        command|builtin|exec|nohup|nice|stdbuf|time|env|xargs|timeout|sudo|doas) ;;
        *) return 1 ;;
    esac
    for x in "${w[@]:k+1}"; do
        [[ "$x" == gh || "$x" == */gh ]] && return 0
    done
    return 1
}

gh_option_expansion() {
    local s="$1" n=${#1} i=0 c nx body
    local sq=false dq=false exp=false first=""
    while (( i < n )); do
        c="${s:i:1}"
        if $sq; then                                # single quotes: all literal
            if [[ "$c" == "'" ]]; then
                sq=false
            elif [[ -z "$first" ]]; then
                first="$c"
            fi
            i=$((i + 1)); continue
        fi
        if ! $dq && [[ "$c" == [[:space:]] ]]; then # a word ends
            if $exp && [[ "$first" == "-" ]]; then return 0; fi
            exp=false; first=""
            i=$((i + 1)); continue
        fi
        case "$c" in
            \\)                                     # an escaped character is literal
                [[ -z "$first" ]] && first="${s:i+1:1}"
                i=$((i + 2)); continue ;;
            "'")
                if ! $dq; then sq=true; i=$((i + 1)); continue; fi ;;
            '"')
                if $dq; then dq=false; else dq=true; fi
                i=$((i + 1)); continue ;;
            '$')
                nx="${s:i+1:1}"
                case "$nx" in
                    "'"|'"')
                        $dq || return 0 ;;          # $'...' and $"..."
                    '{')
                        body="${s:i+2}"; body="${body%%\}*}"
                        [[ "$body" == *[-=+/@]* ]] && return 0
                        exp=true; i=$((i + 3 + ${#body})); continue ;;
                    '('|'[')
                        return 0 ;;
                    [A-Za-z_])
                        exp=true; i=$((i + 2))
                        while [[ "${s:i:1}" == [A-Za-z0-9_] ]]; do i=$((i + 1)); done
                        continue ;;
                    [0-9]|'@'|'*'|'#'|'?'|'$'|'!'|'-')
                        exp=true; i=$((i + 2)); continue ;;
                esac ;;
            '*'|'?'|'[')
                if ! $dq; then                      # an unquoted glob
                    [[ -z "$first" ]] && return 0
                    exp=true; i=$((i + 1)); continue
                fi ;;
            '{')
                if ! $dq; then                      # {a,b} and {a..b}; {owner} is text
                    body="${s:i+1}"; body="${body%%\}*}"
                    if [[ "$body" != "${s:i+1}" && ( "$body" == *,* || "$body" == *..* ) ]]; then
                        return 0
                    fi
                fi ;;
        esac
        [[ -z "$first" ]] && first="$c"
        i=$((i + 1))
    done
    $exp && [[ "$first" == "-" ]]
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
    if is_gh_command "$sub" && gh_option_expansion "$sub"; then
        log "PASS: $COMMAND (an expansion can form a gh option, prompt kept: $sub)"
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
