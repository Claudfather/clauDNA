# Resolving `<claudna-root>`

Shared reference for skills that run a bundled script, or that forward a `_shared` path to another agent. Skills reference this file at `../_shared/claudna-root.md`.

`<claudna-root>` stands for the directory that holds this plugin's `skills/`, `scripts/` and `lib/`. A bundled script is written `<claudna-root>/scripts/<name>`, and a `lib/` entry point `<claudna-root>/lib/<path>`. A `_shared` doc named in text that leaves its file before anyone reads it is written `<claudna-root>/skills/_shared/<path>`. Resolve it before you run or forward anything:

<!-- claudna-root:begin -->
Use the first of these candidates that contains the file you need:

1. **Claude Code only: the path filled in for `${CLAUDE_PLUGIN_ROOT}` in the loaded `SKILL.md` body.** This expansion is not an ordinary shell variable. Skip a literal, unfilled value; Codex must not use this Claude-only expansion candidate.
2. **`$CLAUDNA_ROOT`**, when explicitly set by the operator, or a host-provided `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` when actually set. Validate the needed bundled file before accepting this override. Ordinary skill shells must not assume a hook environment exists.
3. **`<skill-dir>/../..`**, derived from the actual absolute path of the loaded skill. This is the default on Codex when no valid operator override exists. Keep spaces intact; never infer this path from cwd.
4. **Claude Code only: the highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/`.** Compare the version directories as version numbers, not as text: `0.19.0` is above `0.9.0`. Codex must not use the Claude cache fallback; it could select an unrelated or unloaded copy.

If none of them contains the file, stop and say so. Never fall back to a path in the working directory, which is the user's project, not this plugin. Substitute the resolved absolute root and quote paths in commands. Before forwarding a prompt, replace every `<claudna-root>` with that root and fill all task placeholders; the receiving agent cannot resolve the caller's installation.
<!-- claudna-root:end -->
