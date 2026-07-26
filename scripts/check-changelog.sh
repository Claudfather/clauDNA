#!/usr/bin/env bash
# Changelog gate: CHANGELOG.md must gain new [Unreleased] content relative
# to origin/main. Part of the `make check` check-set (see Makefile); CI
# runs this same script via `make check`.
set -euo pipefail

# With no commits relative to origin/main there is no change to gate
# (e.g. `make check` on main itself). A CI PR run executes on a merge
# commit, which is never equal to origin/main, so the gate always
# enforces there.
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main 2>/dev/null || echo unknown)" ]; then
    echo "HEAD == origin/main; nothing to gate"
    exit 0
fi

if ! grep -q '## \[Unreleased\]' CHANGELOG.md; then
    echo "::error::CHANGELOG.md missing [Unreleased] section"
    exit 1
fi

# Extract [Unreleased] content from the working tree
pr_content=$(sed -n '/^## \[Unreleased\]/,/^## \[/{ /^## \[/!p; }' CHANGELOG.md)

# Extract [Unreleased] content from main
main_changelog=$(mktemp)
trap 'rm -f "$main_changelog"' EXIT
git show origin/main:CHANGELOG.md > "$main_changelog" 2>/dev/null || true
main_content=$(sed -n '/^## \[Unreleased\]/,/^## \[/{ /^## \[/!p; }' "$main_changelog")

if [ "$pr_content" = "$main_content" ]; then
    echo "::error::CHANGELOG.md [Unreleased] section has no new content compared to main"
    exit 1
fi

echo "Changelog has new unreleased content"
