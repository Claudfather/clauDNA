## What changed

<!-- Describe the change in 1-3 sentences. What does this PR do? -->

## Why

<!-- What problem does this solve? Link to an issue if applicable: Closes #123 -->

## Testing done

<!-- How did you verify this works? -->

- [ ] Tested locally with `claude --plugin-dir /path/to/clauDNA`
- [ ] `python3 scripts/validate-skills.py` passes
- [ ] `python3 scripts/validate-manifest.py` passes
- [ ] `python3 -m pytest tests/` passes (if test files changed)

## Checklist

- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Version bump in `.claude-plugin/plugin.json` (if this changes user-facing behavior)
- [ ] No hardcoded paths, tokens, or credentials
