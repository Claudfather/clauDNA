#!/bin/bash
# clauDNA install script
# Sets up global Claude Code configuration with collision detection and backup

set -e

echo "=== clauDNA installer ==="
echo "(Tip: You can also run 'claude' from this repo and use /clauDNA-setup)"
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# --- Collision Detection ---
COLLISIONS=()
for file in "$SCRIPT_DIR"/global/commands/*.md; do
    name=$(basename "$file")
    if [ -f "$HOME/.claude/commands/$name" ]; then
        COLLISIONS+=("commands/$name")
    fi
done
for dir in "$SCRIPT_DIR"/global/skills/*/; do
    name=$(basename "$dir")
    if [ -f "$HOME/.claude/skills/$name/SKILL.md" ]; then
        COLLISIONS+=("skills/$name/")
    fi
done
for file in "$SCRIPT_DIR"/global/agents/*.md; do
    name=$(basename "$file")
    if [ -f "$HOME/.claude/agents/$name" ]; then
        COLLISIONS+=("agents/$name")
    fi
done
for file in "$SCRIPT_DIR"/global/hooks/*.sh; do
    name=$(basename "$file")
    if [ -f "$HOME/.claude/hooks/$name" ]; then
        COLLISIONS+=("hooks/$name")
    fi
done

if [ ${#COLLISIONS[@]} -gt 0 ]; then
    echo "Collisions detected — these local files will be overwritten:"
    for c in "${COLLISIONS[@]}"; do
        echo "  ~/.claude/$c"
    done
    echo ""
fi

# --- Backup ---
HAS_EXISTING=false
for dir in commands skills agents hooks; do
    if [ -d "$HOME/.claude/$dir" ] && [ "$(ls -A "$HOME/.claude/$dir" 2>/dev/null)" ]; then
        HAS_EXISTING=true
        break
    fi
done

if [ "$HAS_EXISTING" = true ]; then
    BACKUP_DIR="$HOME/.local/share/clauDNA/backups/$(date +%Y-%m-%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    cp -r "$HOME/.claude/commands" "$BACKUP_DIR/commands" 2>/dev/null || true
    cp -r "$HOME/.claude/skills" "$BACKUP_DIR/skills" 2>/dev/null || true
    cp -r "$HOME/.claude/agents" "$BACKUP_DIR/agents" 2>/dev/null || true
    cp -r "$HOME/.claude/hooks" "$BACKUP_DIR/hooks" 2>/dev/null || true
    echo "Backed up existing files to $BACKUP_DIR"
    echo ""
fi

# --- Create Directory Structure ---
echo "Creating directories..."
mkdir -p ~/.claude/{commands,skills,agents,hooks,notes/{projects,patterns,decisions,lessons},docs}
mkdir -p ~/.snowflake

# Write breadcrumb so /clauDNA-sync skill can find this repo
echo "$SCRIPT_DIR" > ~/.claude/.clauDNA-repo

# --- Copy Files ---
echo "Installing global commands..."
cp "$SCRIPT_DIR"/global/commands/*.md ~/.claude/commands/

echo "Installing global skills..."
for dir in "$SCRIPT_DIR"/global/skills/*/; do
    name=$(basename "$dir")
    mkdir -p "$HOME/.claude/skills/$name"
    cp -r "$dir"* "$HOME/.claude/skills/$name/"
done

echo "Installing global agents..."
cp "$SCRIPT_DIR"/global/agents/*.md ~/.claude/agents/

echo "Installing hooks..."
cp "$SCRIPT_DIR"/global/hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh

# NOTE: We intentionally do NOT overwrite ~/.claude/settings.json
# Users manage their own global settings (permissions, model, hooks).
# See global/settings.json for a reference example.
echo "Skipping settings.json (user-managed — see global/settings.json for reference)"

# --- Permissions Merge ---
# Offer to add recommended permissions to settings.json (additive only)
if command -v jq &>/dev/null; then
    RECOMMENDED="$SCRIPT_DIR/global/recommended-permissions.json"
    SETTINGS="$HOME/.claude/settings.json"

    if [ -f "$RECOMMENDED" ]; then
        # Get all default=true permissions from recommended-permissions.json
        RECOMMENDED_PERMS=$(jq -r '[.categories[] | select(.default == true) | .permissions[]] | unique | .[]' "$RECOMMENDED")

        # Read current allow array (or empty if no settings.json)
        if [ -f "$SETTINGS" ]; then
            if ! jq empty "$SETTINGS" 2>/dev/null; then
                echo "Warning: ~/.claude/settings.json is not valid JSON. Skipping permissions merge."
                RECOMMENDED_PERMS=""
            else
                CURRENT_PERMS=$(jq -r '(.permissions.allow // [])[]' "$SETTINGS" 2>/dev/null || echo "")
            fi
        else
            CURRENT_PERMS=""
        fi

        if [ -n "$RECOMMENDED_PERMS" ]; then
            # --- Pass 1: Detect and offer migration of deprecated colon syntax ---
            COLON_PERMS=()
            if [ -n "$CURRENT_PERMS" ]; then
                while IFS= read -r perm; do
                    case "$perm" in
                        Bash\(*:*\)) COLON_PERMS+=("$perm") ;;
                    esac
                done <<< "$CURRENT_PERMS"
            fi

            if [ ${#COLON_PERMS[@]} -gt 0 ]; then
                echo ""
                echo "Deprecated syntax: ${#COLON_PERMS[@]} permissions use Bash(cmd:*) — deprecated"
                echo "  Modern syntax is Bash(cmd *) (space instead of colon)."
                echo "  The colon syntax may cause permission matching failures."
                echo ""
                for cp in "${COLON_PERMS[@]}"; do
                    MODERN=$(echo "$cp" | sed 's/Bash(\([^:)]*\):/Bash(\1 /')
                    echo "  $cp  →  $MODERN"
                done
                echo ""
                read -p "Migrate to modern syntax? [Y/n] " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                    jq '(.permissions.allow // []) |= [.[] | if test("^Bash\\([^:)]+:") then sub("^Bash\\((?<cmd>[^:)]+):"; "Bash(\(.cmd) ") else . end]' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                    echo "Migrated ${#COLON_PERMS[@]} permissions to modern syntax."
                    # Refresh current perms after migration
                    CURRENT_PERMS=$(jq -r '(.permissions.allow // [])[]' "$SETTINGS" 2>/dev/null || echo "")
                else
                    echo "Skipped syntax migration."
                fi
            fi

            # --- Pass 2: Find missing permissions with deprecated-syntax labeling ---
            MISSING=()
            DEPRECATED_MATCH=()
            while IFS= read -r perm; do
                FOUND=false
                # Check exact match
                if echo "$CURRENT_PERMS" | grep -qxF "$perm"; then
                    FOUND=true
                fi
                # Check deprecated colon syntax match
                if [ "$FOUND" = false ]; then
                    ALT=$(echo "$perm" | sed 's/Bash(\(.*\) /Bash(\1:/')
                    if [ "$ALT" != "$perm" ] && echo "$CURRENT_PERMS" | grep -qxF "$ALT"; then
                        DEPRECATED_MATCH+=("$perm")
                        FOUND=true
                    fi
                fi
                if [ "$FOUND" = false ]; then
                    MISSING+=("$perm")
                fi
            done <<< "$RECOMMENDED_PERMS"

            # Report deprecated-syntax matches separately
            if [ ${#DEPRECATED_MATCH[@]} -gt 0 ]; then
                echo ""
                echo "⚠  ${#DEPRECATED_MATCH[@]} permissions present but using deprecated colon syntax:"
                for dp in "${DEPRECATED_MATCH[@]}"; do
                    echo "   $dp — covered via deprecated Bash(cmd:*) form"
                done
                echo "   Run /clauDNA-setup from Claude Code for interactive migration."
            fi

            if [ ${#MISSING[@]} -gt 0 ]; then
                echo ""
                echo "Recommended permissions: ${#MISSING[@]} missing from ~/.claude/settings.json"
                echo "  (These reduce approval prompts for common tools)"
                echo ""
                for m in "${MISSING[@]}"; do
                    echo "  + $m"
                done
                echo ""
                read -p "Add these recommended permissions? [Y/n] " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                    # Build JSON array of missing permissions
                    MISSING_JSON=$(printf '%s\n' "${MISSING[@]}" | jq -R . | jq -s .)

                    if [ -f "$SETTINGS" ]; then
                        # Merge into existing settings.json
                        jq --argjson new "$MISSING_JSON" '.permissions.allow = ((.permissions.allow // []) + $new | unique)' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                    else
                        # Create minimal settings.json
                        jq -n --argjson perms "$MISSING_JSON" '{"permissions": {"allow": $perms}}' > "$SETTINGS"
                    fi
                    echo "Added ${#MISSING[@]} permissions to ~/.claude/settings.json"
                else
                    echo "Skipped permissions merge."
                    echo "  Run /clauDNA-setup from Claude Code for interactive per-category selection."
                fi
            else
                echo "All recommended permissions already present in settings.json."
            fi
        fi
    fi
    # --- Settings Defaults (statusLine & hooks) ---
    if [ -f "$SETTINGS" ]; then
        REFERENCE="$SCRIPT_DIR/global/settings.json"
        NEEDS_STATUSLINE=false
        NEEDS_HOOKS=false

        # Check if statusLine is configured
        if ! jq -e '.statusLine' "$SETTINGS" >/dev/null 2>&1; then
            NEEDS_STATUSLINE=true
        fi

        # Check if hooks are configured
        if ! jq -e '.hooks' "$SETTINGS" >/dev/null 2>&1; then
            NEEDS_HOOKS=true
        fi

        if [ "$NEEDS_STATUSLINE" = true ] || [ "$NEEDS_HOOKS" = true ]; then
            echo ""
            echo "Settings defaults: activate hook scripts installed in ~/.claude/hooks/"
            if [ "$NEEDS_STATUSLINE" = true ]; then
                echo "  + statusLine  → shows branch, lines changed, model, context %"
            fi
            if [ "$NEEDS_HOOKS" = true ]; then
                echo "  + hooks       → auto-format on Write/Edit, macOS notifications"
            fi
            echo ""
            read -p "Add these settings defaults? [Y/n] " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                if [ "$NEEDS_STATUSLINE" = true ]; then
                    STATUSLINE_JSON=$(jq '.statusLine' "$REFERENCE")
                    jq --argjson sl "$STATUSLINE_JSON" '.statusLine = $sl' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                    echo "Added statusLine config"
                fi
                if [ "$NEEDS_HOOKS" = true ]; then
                    HOOKS_JSON=$(jq '.hooks' "$REFERENCE")
                    jq --argjson hk "$HOOKS_JSON" '.hooks = $hk' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                    echo "Added hooks config"
                fi
            else
                echo "Skipped settings defaults."
            fi
        else
            echo "statusLine and hooks already configured in settings.json."
        fi

        # Check if hooks exist but PreToolUse is missing
        NEEDS_PRETOOLUSE=false
        if jq -e '.hooks' "$SETTINGS" >/dev/null 2>&1; then
            if ! jq -e '.hooks.PreToolUse' "$SETTINGS" >/dev/null 2>&1; then
                NEEDS_PRETOOLUSE=true
            fi
        fi

        if [ "$NEEDS_PRETOOLUSE" = true ]; then
            echo ""
            echo "PreToolUse hook: auto-approve compound commands where all parts are in allow list"
            echo "  + hooks.PreToolUse → resolves permission prompts for &&, |, and file-modifying commands"
            echo ""
            read -p "Add PreToolUse hook? [Y/n] " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                PRETOOLUSE_JSON=$(jq '.hooks.PreToolUse' "$REFERENCE")
                jq --argjson ptu "$PRETOOLUSE_JSON" '.hooks.PreToolUse = $ptu' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                echo "Added PreToolUse hook config"
            else
                echo "Skipped PreToolUse hook."
            fi
        fi

        # --- Sandbox Configuration (Opt-In) ---
        if ! jq -e '.sandbox' "$SETTINGS" >/dev/null 2>&1; then
            echo ""
            echo "Sandbox Configuration (Recommended)"
            echo "  Eliminates ~84% of permission prompts"
            echo "  Bash commands in project dir → auto-approved (sandboxed)"
            echo "  Read/Write/Edit tools → unaffected"
            echo "  Cross-directory Bash → falls through to normal prompt"
            echo ""
            read -p "Enable sandbox? [Y/n] " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                SANDBOX_JSON=$(jq '.sandbox' "$REFERENCE")
                jq --argjson sb "$SANDBOX_JSON" '.sandbox = $sb' "$SETTINGS" > "${SETTINGS}.tmp" && mv "${SETTINGS}.tmp" "$SETTINGS"
                echo "Added sandbox config (enabled + autoAllowBashIfSandboxed)"
            else
                echo "Skipped sandbox configuration."
            fi
        else
            echo "Sandbox already configured in settings.json."
        fi
    fi
else
    echo ""
    echo "Note: jq is not installed. Skipping permissions merge and settings defaults."
    echo "  Install jq: brew install jq (macOS) or apt install jq (Linux)"
    echo "  Or run /clauDNA-setup from Claude Code for interactive setup."
fi

# Create starter lessons file if it doesn't exist
if [ ! -f ~/.claude/notes/lessons/global.md ]; then
    echo "Creating global lessons file..."
    cat > ~/.claude/notes/lessons/global.md << 'EOF'
# Global Lessons

Patterns and rules learned from corrections. Review at session start.

---

_Add lessons below this line after corrections_
EOF
fi

# Copy documentation
echo "Installing documentation..."
cp "$SCRIPT_DIR"/SETUP_GUIDE.md ~/.claude/docs/
cp "$SCRIPT_DIR"/CLAUDE_MD_TEMPLATE.md ~/.claude/docs/

echo ""
echo "=== Installation complete ==="
echo ""
echo "Installed to ~/.claude/:"
SKILL_COUNT=$(ls -d ~/.claude/skills/*/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
CMD_COUNT=$(ls ~/.claude/commands/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "  - skills/       ($SKILL_COUNT skills)"
echo "  - commands/     ($CMD_COUNT commands)"
echo "  - agents/       ($(ls ~/.claude/agents/*.md 2>/dev/null | wc -l | tr -d ' ') agents)"
echo "  - hooks/        ($(ls ~/.claude/hooks/*.sh 2>/dev/null | wc -l | tr -d ' ') hooks)"
echo "  - settings.json  (skipped — user-managed)"
echo "  - docs/"
echo "  - .clauDNA-repo  (breadcrumb → $SCRIPT_DIR)"
if [ -n "$BACKUP_DIR" ]; then
    echo "  - backup         ($BACKUP_DIR)"
fi
# --- Legacy Command Detection ---
LEGACY_COUNT=0
SUPERSEDED_COUNT=0
for file in "$HOME"/.claude/commands/*.md; do
    [ -f "$file" ] || continue
    name=$(basename "$file" .md)
    LEGACY_COUNT=$((LEGACY_COUNT + 1))
    if [ -f "$HOME/.claude/skills/$name/SKILL.md" ]; then
        SUPERSEDED_COUNT=$((SUPERSEDED_COUNT + 1))
    fi
done
if [ "$SUPERSEDED_COUNT" -gt 0 ]; then
    echo ""
    echo "Legacy Commands Detected"
    echo "═══════════════════════════════════════════"
    echo "  ~/.claude/commands/ contains $LEGACY_COUNT .md files"
    echo "  $SUPERSEDED_COUNT have skill equivalents (skills take precedence)"
    echo "  Run /clauDNA-migrate to clean up"
    echo "═══════════════════════════════════════════"
fi

echo ""
echo "=== Next steps ==="
echo ""
echo "1. SNOWFLAKE SETUP (if not done already):"
echo "   See SETUP_GUIDE.md Section 5 for key pair authentication"
echo "   - Generate keys: openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/rsa_key.p8 -nocrypt"
echo "   - Have admin register your public key"
echo "   - Configure ~/.snowsql/config (see snowflake/snowsql-config-template)"
echo ""
echo "2. SHELL ALIASES:"
echo "   cat $SCRIPT_DIR/shell/zshrc-additions.sh >> ~/.zshrc"
echo "   source ~/.zshrc"
echo ""
echo "3. PROJECT SETUP (for each project):"
echo "   cp -r $SCRIPT_DIR/project-template/.claude /path/to/project/"
echo "   cp $SCRIPT_DIR/project-template/CLAUDE.md /path/to/project/"
echo "   Then customize CLAUDE.md for that project"
echo ""
echo "Full documentation: ~/.claude/docs/SETUP_GUIDE.md"
