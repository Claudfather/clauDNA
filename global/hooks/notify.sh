#!/bin/bash
# Send macOS notification when Claude needs attention
# Used by the Notification hook

# Get the message from stdin or use default
MESSAGE=$(cat)
if [ -z "$MESSAGE" ]; then
    MESSAGE="Claude needs your attention"
fi

# Send notification via osascript
osascript -e "display notification \"$MESSAGE\" with title \"Claude Code\""
