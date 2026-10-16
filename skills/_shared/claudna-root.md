# Resolving `<claudna-root>`

Shared reference for skills that run a bundled script, or that forward a `_shared` path to another agent. Skills reference this file at `../_shared/claudna-root.md`.

`<claudna-root>` stands for the directory that holds this plugin's `skills/`, `scripts/` and `lib/`. A bundled script is written `<claudna-root>/scripts/<name>`, and a `lib/` entry point `<claudna-root>/lib/<path>`. A `_shared` doc named in text that leaves its file before anyone reads it is written `<claudna-root>/skills/_shared/<path>`. Resolve it before you run or forward anything:

<!-- claudna-root:begin -->
Use the first candidate that contains the bundled file you actually need:

1. **The actual absolute root derived from the loaded skill path**: two directories above its containing directory. Use the path the host supplied, including spaces; never infer it from cwd.
2. **An explicitly set operator root** (`CLAUDNA_ROOT`, or a host-provided `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`), after checking the needed file exists there. Ordinary skill shells must not assume hook environment variables exist.
3. **The path Claude Code filled in for `${CLAUDE_PLUGIN_ROOT}`**, only in a `SKILL.md` body. In other files it stays literal; never pass an unfilled variable to the shell.
4. **Claude Code only:** the highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/`, comparing semantic versions. Codex must not use the Claude cache fallback; it could select an unrelated or unloaded copy.

If no valid candidate contains the file, stop and report that missing file. Never run a same-named helper from the project working directory. Substitute the resolved absolute root and quote paths in commands. Before forwarding a prompt, replace every `<claudna-root>` with that root and fill all task placeholders; the receiving agent cannot resolve the caller's installation.
<!-- claudna-root:end -->
