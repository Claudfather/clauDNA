# Resolving `<claudna-root>`

Shared reference for skills that run a bundled script, or that forward a `_shared` path to another agent. Skills reference this file at `../_shared/claudna-root.md`.

`<claudna-root>` stands for the directory that holds this plugin's `skills/`, `scripts/` and `lib/`. A bundled script is written `<claudna-root>/scripts/<name>`, and a `lib/` entry point `<claudna-root>/lib/<path>`. A `_shared` doc named in text that leaves its file before anyone reads it is written `<claudna-root>/skills/_shared/<path>`. Resolve it before you run or forward anything:

<!-- claudna-root:begin -->
Use the first of these candidates that contains the file you need:

1. **The path Claude Code filled in for `${CLAUDE_PLUGIN_ROOT}`.** Claude Code does this only in a `SKILL.md` body, fenced blocks included. In any other file the variable stays literal, and the shell never has it set.
2. **`$CLAUDNA_ROOT`**, when your host or operator sets it.
3. **`<skill-dir>/../..`**, two directories above the directory of the skill you are running. Claude Code prints that directory as "Base directory for this skill"; any other host knows where it loaded `SKILL.md` from.
4. **The highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/`**, Claude Code's plugin cache. Compare the version directories as version numbers, not as text: `0.19.0` is above `0.9.0` (`sort -V` orders them so). It comes last because it can hold a newer copy than the one that is loaded.

If none of them contains the file, stop and say so. Never fall back to a path in the working directory, which is the user's project, not this plugin. Write the resolved absolute path into the command, and keep the command a bare one. In a prompt you forward to another agent, replace `<claudna-root>` with the absolute path before you send it, because the receiving agent has no skill directory to resolve against.
<!-- claudna-root:end -->
