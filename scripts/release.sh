#!/usr/bin/env bash
# release.sh — bump version, update CHANGELOG, commit, tag.
#
# Usage:
#   ./scripts/release.sh patch          # 0.3.0 → 0.3.1
#   ./scripts/release.sh minor          # 0.3.0 → 0.4.0
#   ./scripts/release.sh major          # 0.3.0 → 1.0.0
#   ./scripts/release.sh --dry-run patch  # preview without writing
#
# Does NOT push. Leaves that to the human.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_JSON="$REPO_ROOT/.claude-plugin/plugin.json"
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

# --- Arg parsing ---

DRY_RUN=false
BUMP_TYPE=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        major|minor|patch) BUMP_TYPE="$arg" ;;
        -h|--help)
            echo "Usage: ./scripts/release.sh [--dry-run] <major|minor|patch>"
            exit 0
            ;;
        *)
            echo "error: unknown argument '$arg'" >&2
            echo "Usage: ./scripts/release.sh [--dry-run] <major|minor|patch>" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$BUMP_TYPE" ]]; then
    echo "error: bump type required (major, minor, or patch)" >&2
    echo "Usage: ./scripts/release.sh [--dry-run] <major|minor|patch>" >&2
    exit 1
fi

# --- Pre-flight checks ---

if ! command -v jq &>/dev/null; then
    echo "error: jq is required but not installed" >&2
    exit 1
fi

if [[ ! -f "$PLUGIN_JSON" ]]; then
    echo "error: $PLUGIN_JSON not found" >&2
    exit 1
fi

if [[ ! -f "$CHANGELOG" ]]; then
    echo "error: $CHANGELOG not found" >&2
    exit 1
fi

# Clean working tree check
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    echo "error: working tree is dirty — commit or stash changes first" >&2
    git -C "$REPO_ROOT" status --short >&2
    exit 1
fi

# --- Read current version ---

CURRENT_VERSION="$(jq -r '.version' "$PLUGIN_JSON")"
if [[ -z "$CURRENT_VERSION" || "$CURRENT_VERSION" == "null" ]]; then
    echo "error: could not read version from $PLUGIN_JSON" >&2
    exit 1
fi

# Parse semver components
IFS='.' read -r V_MAJOR V_MINOR V_PATCH <<< "$CURRENT_VERSION"

if ! [[ "$V_MAJOR" =~ ^[0-9]+$ && "$V_MINOR" =~ ^[0-9]+$ && "$V_PATCH" =~ ^[0-9]+$ ]]; then
    echo "error: current version '$CURRENT_VERSION' is not valid semver" >&2
    exit 1
fi

# --- Compute new version ---

case "$BUMP_TYPE" in
    major) NEW_VERSION="$((V_MAJOR + 1)).0.0" ;;
    minor) NEW_VERSION="$V_MAJOR.$((V_MINOR + 1)).0" ;;
    patch) NEW_VERSION="$V_MAJOR.$V_MINOR.$((V_PATCH + 1))" ;;
esac

# --- Check CHANGELOG has unreleased entries ---

# Extract content between ## [Unreleased] and the next ## [x.y.z] header
UNRELEASED_CONTENT="$(awk '
    /^## \[Unreleased\]/ { found=1; next }
    found && /^## \[/ { exit }
    found { print }
' "$CHANGELOG")"

# Strip blank lines and check if anything substantive remains
UNRELEASED_TRIMMED="$(printf '%s' "$UNRELEASED_CONTENT" | sed '/^[[:space:]]*$/d')"

if [[ -z "$UNRELEASED_TRIMMED" ]]; then
    echo "error: CHANGELOG has no entries under [Unreleased] — nothing to release" >&2
    echo "hint: add entries under '## [Unreleased]' before running release" >&2
    exit 1
fi

# --- Summary ---

RELEASE_DATE="$(date +%Y-%m-%d)"
TAG="v$NEW_VERSION"

echo "Release summary:"
echo "  current version:  $CURRENT_VERSION"
echo "  new version:      $NEW_VERSION ($BUMP_TYPE bump)"
echo "  tag:              $TAG"
echo "  date:             $RELEASE_DATE"
echo ""
echo "Unreleased entries:"
printf '%s\n' "$UNRELEASED_TRIMMED" | head -20
TOTAL_LINES="$(printf '%s\n' "$UNRELEASED_TRIMMED" | wc -l)"
if [[ "$TOTAL_LINES" -gt 20 ]]; then
    echo "  ... ($((TOTAL_LINES - 20)) more lines)"
fi
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] would update plugin.json, CHANGELOG.md, commit, and tag $TAG"
    exit 0
fi

# --- Update plugin.json ---

TMP_PLUGIN="$(mktemp)"
jq --arg ver "$NEW_VERSION" '.version = $ver' "$PLUGIN_JSON" > "$TMP_PLUGIN"
mv "$TMP_PLUGIN" "$PLUGIN_JSON"

echo "updated $PLUGIN_JSON → $NEW_VERSION"

# --- Update CHANGELOG.md ---

# Replace the [Unreleased] section: keep the header, insert the new version
# header with the unreleased content below it, then a fresh empty [Unreleased].
TMP_CHANGELOG="$(mktemp)"

awk -v new_ver="$NEW_VERSION" -v release_date="$RELEASE_DATE" '
    /^## \[Unreleased\]/ {
        print "## [Unreleased]"
        print ""
        print "## [" new_ver "] - " release_date
        skip_blanks = 1
        next
    }
    # Skip leading blank lines right after [Unreleased] that we already printed
    skip_blanks && /^[[:space:]]*$/ { next }
    skip_blanks { skip_blanks = 0 }
    { print }
' "$CHANGELOG" > "$TMP_CHANGELOG"
mv "$TMP_CHANGELOG" "$CHANGELOG"

echo "updated $CHANGELOG — moved unreleased entries under [$NEW_VERSION]"

# --- Git commit + tag ---

git -C "$REPO_ROOT" add "$PLUGIN_JSON" "$CHANGELOG"
git -C "$REPO_ROOT" commit -m "release: v$NEW_VERSION"
git -C "$REPO_ROOT" tag -a "$TAG" -m "Release $TAG"

echo ""
echo "committed and tagged $TAG"
echo ""
echo "Ready to push. Review the commit, then:"
echo "  git push origin main --follow-tags"
