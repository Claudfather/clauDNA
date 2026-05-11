---
name: notifications
description: "Use when you want to configure macOS or iTerm2 notifications for Claude Code sessions."
user-invocable: false
---

# Notification Setup

Get notified when Claude needs your attention.

## Automatic Notifications

A notification hook is configured in `~/.claude/settings.json` that sends a macOS notification when Claude needs input.

## iTerm2 Built-in Notifications (Recommended)

For even better notifications, enable iTerm2's built-in alert:

1. **Open iTerm2 Preferences** (⌘,)
2. Go to **Profiles** → **Terminal**
3. Check **"Send notification when idle"**
4. Set idle time (e.g., 5 seconds)

Now iTerm2 will notify you when any terminal tab has been waiting for input.

### Additional iTerm2 Tips

**Tab Naming:**
Right-click a tab → "Edit Tab Title" to name your Claude sessions (e.g., "Claude 1 - Feature A")

**Tab Colors:**
Right-click a tab → "Tab Color" to color-code different worktrees/tasks

**Badge:**
Show current directory or custom text in the terminal background:
- Profiles → General → Badge → `\(session.path)`

## Terminal Notification Command

You can also manually trigger a notification:
```bash
osascript -e 'display notification "Message here" with title "Claude Code"'
```

## Testing

To test the notification hook works, Claude will trigger it when asking for input during long-running tasks.
