# shellcheck shell=bash
# clauDNA's state root, shared by every hook that keeps state (sourced, not run).
#
# One root for everything clauDNA stores on a machine: ${CLAUDNA_STATE_DIR:-~/.claudna}.
# Session payload lives under sessions/<sid>/; bounded bootstrap codes under hooks/. It mirrors
# lib/claudna/session_store/paths.py (a parity test holds them together): a
# leading ~ expands, and a relative CLAUDNA_STATE_DIR is rejected,
# because hooks run inside the user's project and a relative root would put
# private state in a repository that can be committed.
#
# claudna_state_dir prints the root, or nothing when there is no safe one (no
# HOME, or a relative override). Callers treat nothing as "keep no state" and
# fail open.
claudna_state_dir() {
    local root="${CLAUDNA_STATE_DIR:-${HOME:+$HOME/.claudna}}"
    case "$root" in
        "~") root="${HOME:-~}" ;;
        "~/"*) root="${HOME:+$HOME/${root#"~/"}}" ;;
    esac
    case "$root" in
        /*) printf '%s' "$root" ;;
        *) return 0 ;;
    esac
}

# Resolve one native session's directory without creating it. Keep this grammar
# byte-for-byte aligned with paths.validate_sid: ASCII, 1–128 safe characters,
# starting with an alphanumeric. No caller may substitute or guess an ID.
claudna_session_dir() {
    local sid="${1-}" root
    local LC_ALL=C
    if (( $# != 1 )) || [[ ! "$sid" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
        return 0
    fi
    root="$(claudna_state_dir)"
    [[ "$root" == /* ]] || return 0
    printf '%s/sessions/%s' "$root" "$sid"
}

# Validate JSON before command substitution: shells strip trailing newlines and
# cannot represent NUL. Invalid bytes must never become a different valid owner.
# This helper has no Python dependency; callers may use the directory CLI when
# jq is unavailable and their own workflow already permits Python.
claudna_event_session_id() {
    jq -er '.session_id | select(type == "string") |
        select(length >= 1 and length <= 128) |
        select(test("^[A-Za-z0-9]") and (test("[^A-Za-z0-9._-]") | not))'
}

# No arbitrary stderr, command, path or session identity belongs in bootstrap
# diagnostics. Callers select a fixed code, and every retained line counts one
# failure. This works even when the Python runtime cannot start.
claudna_bootstrap_error() {
    local code="${1-}" root log
    case "$code" in
        session_store_runtime|telemetry_configuration|telemetry_runtime|delegation_runtime) ;;
        *) return 0 ;;
    esac
    root="$(claudna_state_dir)"
    [ -n "$root" ] || return 0
    (
        umask 077
        mkdir -p -m 700 "$root/hooks" 2>/dev/null || exit 0
        log="$root/hooks/bootstrap.log"
        if [ -f "$log" ] && [ "$(wc -c < "$log" 2>/dev/null || echo 0)" -gt 1048576 ]; then
            mv -f "$log" "$log.old" 2>/dev/null || :
        fi
        printf '{"code":"%s","count":1}\n' "$code" >> "$log"
    ) 2>/dev/null || :
}
