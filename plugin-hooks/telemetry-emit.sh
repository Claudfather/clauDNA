#!/bin/bash
# Retired in 0.23 (session store phase 4): a no-op, kept for one release.
#
# Skill telemetry for Claudosseum is now written by the session store's
# PostToolUse hook (lib/claudna/session_store/telemetry.py, wired through
# plugin-hooks/session-store.sh). Same opt-in (CLAUDNA_TELEMETRY=1), same path
# (CLAUDNA_TELEMETRY_PATH, default ~/.claude/telemetry/skill-events.jsonl), same
# line shape, with real `success`, `duration_ms` and `session_id` values.
#
# This file stays only so a settings.json that wired it by hand keeps working;
# the plugin no longer runs it. It will be removed in the next release.
exit 0
