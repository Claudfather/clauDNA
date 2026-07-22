#!/bin/bash
# Send macOS notification when Claude needs attention
# Used by the Notification hook

# Extract only the notification message from the hook's JSON payload. Reading
# raw stdin and interpolating it into the AppleScript below is an injection
# sink (a `"` + newline in the message escapes the string literal and can run
# `do shell script`), and is also broken for normal input, since the JSON
# envelope itself contains quotes. Pull the one field we mean to display.
INPUT=$(cat)
MESSAGE=""
if command -v jq >/dev/null 2>&1; then
    MESSAGE=$(printf '%s' "$INPUT" | jq -r '.message // empty' 2>/dev/null)
fi
if [ -z "$MESSAGE" ]; then
    MESSAGE="Claude needs your attention"
fi

# Pass the message as a run-argument bound to an AppleScript variable — data,
# never code. The `-e` fragments are static, so no message content can alter
# what AppleScript executes; `--` stops an argument that begins with `-` from
# being read as an option.
osascript \
    -e 'on run {m}' \
    -e 'display notification m with title "Claude Code"' \
    -e 'end run' \
    -- "$MESSAGE"
