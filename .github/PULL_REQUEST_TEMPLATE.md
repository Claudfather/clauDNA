## What changed

<!-- Describe the change in 1-3 sentences. What does this PR do? -->

## Why

<!-- What problem does this solve? Link to an issue if applicable: Closes #123 -->

## Testing done

<!-- How did you verify this works? -->

- [ ] Tested locally with `claude --plugin-dir /path/to/clauDNA`
- [ ] `make check` passes (the exact check-set CI runs)

## Checklist

- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] Version bump in **both** `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json` (if this changes user-facing behavior — the two must match)
- [ ] No hardcoded paths, tokens, or credentials
