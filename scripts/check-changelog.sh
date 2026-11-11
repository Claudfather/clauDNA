#!/usr/bin/env bash
# Keep contributor and versioned-release rules in the release controller.
set -euo pipefail
PYTHONDONTWRITEBYTECODE=1 python3 "$(dirname "${BASH_SOURCE[0]}")/release_candidate.py" --check-changelog
