# shellcheck shell=bash
# clauDNA's state root, shared by every hook that keeps state (sourced, not run).
#
# One root for everything clauDNA stores on a machine: ${CLAUDNA_STATE_DIR:-~/.claudna}.
# The session store lives under sessions/, hook state under hooks/. It mirrors
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
