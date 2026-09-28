#!/usr/bin/env bash
# Cloud Agent repository bootstrap — the `install` command in environment.json.
#
# Installs exactly the toolchain CI installs: `make deps`, which reads the
# pinned requirements-dev.txt. The check-set stays defined once, in the
# Makefile; this script only makes it runnable on a fresh VM.
#
# Idempotent by construction: pip converges on the pinned versions and the
# mkdir is a no-op once the directory exists.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Create the console-script directory BEFORE installing into it.
#
# pip has no writeable system site-packages here, so it defaults to a user
# install and puts `ruff` in ~/.local/bin. The stock ~/.profile prepends that
# directory to PATH only `if [ -d "$HOME/.local/bin" ]`, re-evaluated per login
# shell — so on a VM where it has never existed, the shell that runs first
# drops it, and a tool invoked by bare name is not found. Creating it here means
# every later login shell picks it up, with no profile to edit.
mkdir -p "$HOME/.local/bin"

make deps

# Resolve the toolchain through the same interpreter `make check` uses, so a
# broken install fails here, named, instead of at whichever check-set leg runs
# first.
python3 -m ruff --version
python3 -m pytest --version
