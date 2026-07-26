# Single source of truth for the clauDNA check-set (#303).
#
# CI (.github/workflows/ci.yml) runs exactly `make check`, so a green
# `make check` locally is a green CI run — same commands, same order,
# same pinned toolchain (requirements-dev.txt). Add or change checks
# HERE, never in the workflow.
#
# One-time setup:    make deps
# Pre-push gate:     make check
# Label-gated runs:  PR_LABELS=full-validate make check
#                    (CI forwards PR labels via this env var; consumed
#                    by scripts/skill_checks.py)

.PHONY: check deps check-skills check-integration check-agents check-manifest check-changelog lint test

check: check-skills check-integration check-agents check-manifest check-changelog lint test

deps:
	pip install -r requirements-dev.txt

check-skills:
	python3 scripts/validate-skills.py

check-integration:
	python3 scripts/integration-test.py

check-agents:
	python3 scripts/validate-agents.py

check-manifest:
	python3 scripts/validate-manifest.py

check-changelog:
	bash scripts/check-changelog.sh

lint:
	ruff check scripts/ tests/

test:
	python3 -m pytest tests/
