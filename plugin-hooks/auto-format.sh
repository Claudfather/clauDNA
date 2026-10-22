#!/bin/bash
# Auto-format hook for Claude Code
# Runs after Write/Edit operations to format code.
#
# For Python it changes layout, never code: ruff formats only a file already
# kept in its default style, and no lint fix runs. Whatever any formatter
# changes is reported to the session, so no file changes silently.
#
# Deliberately not `set -e`. The formatters below exit nonzero for legitimate
# reasons — `ruff format` exits 2 on a file that does not parse, as a file can
# mid-edit — so under `-e` that ordinary case would end the hook with a status
# Claude Code gives a meaning to (exit 1 and exit 2, below). Dropping `-e` is
# what keeps those exit codes single-meaninged; it also stops one failing step
# from skipping the rest, such as the change notice.
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

# Scratch space for the style check and the change notice, made on first use.
WORK=""
trap '[ -z "$WORK" ] || rm -rf -- "$WORK"' EXIT

make_work() {
    [ -n "$WORK" ] || WORK=$(mktemp -d 2>/dev/null)
}

# committed_in_ruff_style: true only when HEAD holds a non-empty version of the
# file that `ruff format --isolated` would leave unchanged. That is the evidence
# the file is kept in ruff's default style, and in such a file formatting can
# reach only what the edit changed. Every way of not knowing (no git, not in a
# repo, no commit yet, an untracked or empty file, a committed version ruff
# cannot parse) answers false, and the file stays as the session wrote it.
#
# `git cat-file blob` applies no textconv or filter driver, so a repo's
# attributes cannot change what is read, and `-c core.fsmonitor=` keeps a repo's
# own .git/config from naming a command for git to run (as in session-start.sh).
# `--stdin-filename=` has ruff read stdin as that file; its `=` form keeps a
# path from being read as an option.
committed_in_ruff_style() {
    local dir=. base=$FILE_PATH
    case "$FILE_PATH" in
        */*) dir=${FILE_PATH%/*} base=${FILE_PATH##*/} ;;
    esac
    make_work \
        && git -C "${dir:-/}" -c core.fsmonitor= cat-file blob "HEAD:./$base" > "$WORK/committed" 2>/dev/null \
        && [ -s "$WORK/committed" ] \
        && ruff format --isolated --check --stdin-filename="$FILE_PATH" -- - \
            < "$WORK/committed" > /dev/null 2>&1
}

# format_and_report <name> <command...>: run one formatter on the file and, if
# it changed the file, tell the session. The session's next Edit has to match
# what is on disk, so a hook that changes a file the session just wrote must
# never do it silently. If the file cannot be copied first, the formatter does
# not run: a change it made could not be reported. Formatter output is
# discarded, because this hook's stdout carries the notice. `diff` exits 0 only
# when the file is unchanged.
format_and_report() {
    local name=$1
    shift
    make_work && cp -- "$FILE_PATH" "$WORK/before" 2>/dev/null || return 0
    "$@" > /dev/null 2>&1
    diff -- "$WORK/before" "$FILE_PATH" > "$WORK/diff" 2>/dev/null || report_change "$name"
}

# report_change <name>: print the notice as PostToolUse `additionalContext`,
# which reaches the model as context rather than as an error. It names the lines
# the formatter touched, numbered as the file is now, and how many it added and
# removed, read in one pass over the normal-format diff (POSIX): a `<` line
# left, a `>` line arrived, and a hunk header such as `3,5c3,8`, `4a5,6` or
# `7,9d6` ends with the hunk's lines in the new file. The path is the only text
# not written here, so a quote, backslash or control character in it becomes
# `?`, which keeps the JSON valid.
report_change() {
    local added removed first last where msg path=$FILE_PATH
    read -r added removed first last <<< "$(LC_ALL=C awk '
        /^</ { r++ }
        /^>/ { a++ }
        /^[0-9]/ { sub(/^[0-9,]*[acd]/, ""); n = split($0, p, ","); if (f == "") f = p[1]; l = p[n] }
        END { print a + 0, r + 0, f, l }' "$WORK/diff" 2>/dev/null)"
    path=${path//\\/?}
    path=${path//\"/?}
    path=${path//[[:cntrl:]]/?}
    if [ -n "${first:-}" ]; then
        # A deletion before the first line is numbered 0.
        [ "$first" -gt 0 ] || first=1
        [ "$last" -gt 0 ] || last=1
        where="lines $first-$last"
        [ "$first" != "$last" ] || where="line $first"
        msg="auto-format: $1 changed $where of $path after your edit (+$added/-$removed lines). Read those lines before editing them again."
    else
        msg="auto-format: $1 changed $path after your edit. Read it before editing it again."
    fi
    printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$msg"
}

# Format based on file extension
case "$FILE_PATH" in
    *.py)
        # Python: ruff, formatting only. --isolated: ignore repo config, which
        # can choose where ruff writes (`cache-dir`); -- so a path is never read
        # as an option.
        #
        # Never a lint fix. A lint fix changes code: ruff's default safe fixes
        # include deleting an import that looks unused (F401), and a pytest
        # fixture imported from another module is used only as a parameter name,
        # so its import looks unused. A hook that runs after every edit must
        # never delete code.
        if command -v ruff &> /dev/null && committed_in_ruff_style; then
            format_and_report "ruff format" ruff format --isolated -- "$FILE_PATH"
        fi
        ;;
    *.js|*.jsx|*.ts|*.tsx|*.json|*.md)
        # JavaScript/TypeScript/JSON/Markdown: use prettier if available
        if command -v prettier &> /dev/null; then
            # --no-config: do not load repo config, which is how prettier plugins
            # (repo code) get loaded; -- so a path is never read as an option.
            # Unlike ruff above, prettier formats any file it is given, so in a
            # repo not in prettier's default style it rewrites the whole file;
            # the change is reported.
            format_and_report prettier prettier --write --no-config -- "$FILE_PATH"
        fi
        ;;
    *.sql)
        # SQL: use sqlfluff if available
        if command -v sqlfluff &> /dev/null; then
            # --templater raw: no templating, so a repo .sqlfluff templater cannot
            # run repo code; -- so a path is never read as an option. Unlike the
            # Python path, `sqlfluff fix` applies each enabled rule's fix, so it
            # can change code as well as layout; the change is reported.
            format_and_report "sqlfluff fix" sqlfluff fix --templater raw -- "$FILE_PATH"
        fi
        ;;
esac

exit 0
