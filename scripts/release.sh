#!/usr/bin/env bash
# release.sh — bump, regenerate, commit, qualify the exact commit, then tag.
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
CHANGELOG="$REPO_ROOT/CHANGELOG.md"

# All three manifests carry the version and validate-manifest.py enforces that they
# match, so a release has to move them together. The Claude manifest is the
# one the version is read from.
PLUGIN_JSON="$REPO_ROOT/.claude-plugin/plugin.json"
CURSOR_PLUGIN_JSON="$REPO_ROOT/.cursor-plugin/plugin.json"
CODEX_PLUGIN_JSON="$REPO_ROOT/.codex-plugin/plugin.json"
VERSIONED_MANIFESTS=("$PLUGIN_JSON" "$CURSOR_PLUGIN_JSON" "$CODEX_PLUGIN_JSON")
SUPPORT_CATALOG="$REPO_ROOT/lib/claudna/package_support/catalog.json"
SUPPORT_GUIDE="$REPO_ROOT/documentation/guides/PACKAGE_SUPPORT.md"

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

for manifest in "${VERSIONED_MANIFESTS[@]}"; do
    if [[ ! -f "$manifest" ]]; then
        echo "error: $manifest not found" >&2
        exit 1
    fi
done

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

# Refuse to release from a state the gate already rejects — otherwise the
# release commit inherits a mismatch it did not cause.
for manifest in "${VERSIONED_MANIFESTS[@]}"; do
    manifest_version="$(jq -r '.version' "$manifest")"
    if [[ "$manifest_version" != "$CURRENT_VERSION" ]]; then
        echo "error: manifest versions disagree before the bump" >&2
        echo "hint: reconcile them, then re-run — run 'make check-manifest' to verify" >&2
        exit 1
    fi
done

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

# Verify the same isolated toolchain qualification will use before changing
# any release files. Suppress bytecode so preflight and dry-run stay read-only.
if ! command -v python3 &>/dev/null; then
    echo "error: python3 and the pinned development toolchain in a virtual environment are required — run make deps" >&2
    exit 1
fi
RELEASE_PYTHON="$(PYTHONDONTWRITEBYTECODE=1 python3 "$REPO_ROOT/scripts/release_candidate.py" --preflight)"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
UNRELEASED_TRIMMED="$(cd "$REPO_ROOT" && PYTHONDONTWRITEBYTECODE=1 \
    "$RELEASE_PYTHON" scripts/release_candidate.py --unreleased-notes)"
if ! PYTHONDONTWRITEBYTECODE=1 "$RELEASE_PYTHON" "$REPO_ROOT/scripts/generate_package_support.py" --check; then
    echo "error: package support preflight failed; run make deps, regenerate support, and commit before releasing" >&2
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
    echo "[dry-run] would update all three plugin.json manifests (.claude-plugin/," \
         ".cursor-plugin/, .codex-plugin/), regenerate package support, update CHANGELOG.md," \
         "commit, run exact-candidate source/package qualification, and tag $TAG locally"
    exit 0
fi

# --- Update all three plugin.json manifests ---

for manifest in "${VERSIONED_MANIFESTS[@]}"; do
    TMP_PLUGIN="$(mktemp)"
    jq --arg ver "$NEW_VERSION" '.version = $ver' "$manifest" > "$TMP_PLUGIN"
    mv "$TMP_PLUGIN" "$manifest"
    echo "updated $manifest → $NEW_VERSION"
done

# Source hashes and the displayed version must describe the bumped manifests.
PYTHONDONTWRITEBYTECODE=1 "$RELEASE_PYTHON" "$REPO_ROOT/scripts/generate_package_support.py"

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

# --- Git commit, exact-candidate qualification, then local tag ---

git -C "$REPO_ROOT" add "${VERSIONED_MANIFESTS[@]}" "$CHANGELOG" "$SUPPORT_CATALOG" "$SUPPORT_GUIDE"
git -C "$REPO_ROOT" commit -m "release: v$NEW_VERSION"
CANDIDATE="$(git -C "$REPO_ROOT" rev-parse HEAD)"
# mktemp creates an owned parent; the package output itself must be new.
RELEASE_PARENT="$(mktemp -d "${TMPDIR:-/tmp}/claudna-release.XXXXXX")"
if ! make -C "$REPO_ROOT" tag-release RELEASE_REF="$CANDIDATE" RELEASE_OUTPUT="$RELEASE_PARENT/artifacts"; then
    echo "error: release commit $CANDIDATE was retained; qualification failed and no tag was authorized" >&2
    exit 1
fi

echo ""
echo "qualified and locally tagged $TAG at $CANDIDATE"
echo "artifacts: $RELEASE_PARENT/artifacts"
echo ""
echo "Ready to push. Review the commit, then:"
echo "  git push origin main --follow-tags"
echo ""
echo "The main release workflow independently qualifies its exact candidate."
echo "Existing remote tags must resolve to that same commit; assets cannot be overwritten."
