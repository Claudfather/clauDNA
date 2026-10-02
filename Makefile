# Single source of truth for the clauDNA check-set (#303).
#
# CI (.github/workflows/ci.yml) runs exactly `make check`, so a green
# `make check` locally is a green CI run — same commands, same order,
# same pinned toolchain (requirements-dev.txt). Add or change checks
# HERE, never in the workflow.
#
# Every tool is invoked as `python3 -m <tool>`, never by bare name. `make deps`
# has no writeable system site-packages on most hosts, so pip does a user
# install and the console scripts land in ~/.local/bin — which the stock
# ~/.profile adds to PATH only if it already exists at shell start. Going
# through the interpreter makes the check-set independent of that, and
# guarantees the tools resolve in the same interpreter they were installed for.
#
# One-time setup:    make deps
# Pre-push gate:     make check
# Label-gated runs:  PR_LABELS=full-validate make check
#                    (CI forwards PR labels via this env var; consumed
#                    by scripts/skill_checks.py)

.PHONY: check deps deps-runtime deps-eval test-runtime routing-eval check-skills check-integration check-agents check-manifest check-changelog lint test

check: check-skills check-integration check-agents check-manifest check-changelog lint test

deps:
	python3 -m pip install -r requirements-dev.txt

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
	python3 -m ruff check lib/ scripts/ tests/

test:
	python3 -m pytest tests/

# The runtime floor: hooks and the session store run under the user's own
# python3, which is 3.9 on stock macOS. CI runs these suites on 3.9 too; they
# also pass on any newer Python, so this target works locally as-is.
RUNTIME_TESTS = tests/test_session_store.py tests/test_session_store_hook.py \
	tests/test_session_store_summarize.py tests/test_session_store_harvest.py tests/test_session_store_filing.py \
	tests/test_session_store_lineage.py tests/test_session_store_unclosed.py \
	tests/test_session_store_activity.py tests/test_session_store_readers.py \
	tests/test_session_store_export.py tests/test_session_store_digest.py \
	tests/test_session_store_ops.py \
	tests/test_redact.py tests/test_screen.py tests/test_runtime_layout.py tests/test_precompact_defer.py \
	tests/test_session_start_hook.py

deps-runtime:
	python3 -m pip install -r requirements-runtime-test.txt

test-runtime:
	python3 -m pytest $(RUNTIME_TESTS)

# Live routing evals (scripts/routing_eval.py): paid, so not in `make check`.
# The Claude Code CI evals on is pinned: an upgrade can change the picker or the
# built-in skills it competes with. Raise it on purpose, with an eval run.
# deps-eval is for CI: it replaces the global `claude`. Locally, run
# `make routing-eval` with the Claude Code you have.
CLAUDE_CODE_VERSION = 2.1.287
deps-eval:
	npm install -g @anthropic-ai/claude-code@$(CLAUDE_CODE_VERSION)

ROUTING_EVAL_ARGS ?=
routing-eval:
	python3 scripts/routing_eval.py $(ROUTING_EVAL_ARGS)
