# Scout Prompt Templates

These are the full prompt templates for the 3 parallel recon subagents launched in Step 2c.

**All scouts:** Do not use shell operators (`&&`, `|`, `;`, `2>&1`) — make separate tool calls.

---

## Scout A: Skills Scout

**Prompt for Agent tool:**

> You are scanning a GitHub repo for skill-like patterns.
>
> **Target repo:** `<org>/<repo>`
> **Browse mode:** [API | local clone at `/tmp/heist-<timestamp>/repo/`]
> **Interesting files from tree:** [list of relevant paths]
>
> **If API mode:** Fetch files with `gh api repos/<org>/<repo>/contents/<path>` (returns base64 content — decode it). Alternatively use WebFetch on `https://raw.githubusercontent.com/<org>/<repo>/<branch>/<path>` for raw content.
> **If local mode:** Read files directly from `/tmp/heist-<timestamp>/repo/`. Use Glob and Grep freely.
>
> **Write findings to:** `/tmp/heist-<timestamp>/research/skills-scout.md` using the Write tool. (The Write tool creates parent directories automatically — do not use `mkdir`.)
> **Return only a 2-4 line summary** listing the count and most notable items found.
>
> **What to find:**
>
> 1. **SKILL.md files** — For each: read frontmatter (name, description) and first 30 lines.
> 2. **Command files** — Files in `.claude/commands/` or `commands/`. Record name and purpose.
> 3. **Agent files** — Files in `agents/` or `.claude/agents/`, or `AGENTS.md`. Record persona and capabilities.
> 4. **MCP configurations** — Look for `mcpServers` in JSON/YAML files. Record server names and purpose.
> 5. **Skill-like patterns** — Files with `name:`, `description:`, `allowed-tools` frontmatter that look like skill definitions even if not named SKILL.md.
>
> **Research file format:**
> ```
> # Skills Scout — [repo name]
>
> ## Skills Found
> [For each: name, file path relative to repo root, one-line description, key capabilities]
>
> ## Commands Found
> [For each: name, file path, one-line purpose]
>
> ## Agents Found
> [For each: name, file path, persona description]
>
> ## MCP Configurations
> [For each: server name, what it provides]
>
> ## Notable Patterns
> [Anything interesting about HOW skills are structured]
> ```

---

## Scout B: Config Scout

**Prompt for Agent tool:**

> You are scanning a GitHub repo for configuration patterns relevant to Claude Code or similar AI coding tools.
>
> **Target repo:** `<org>/<repo>`
> **Browse mode:** [API | local clone at `/tmp/heist-<timestamp>/repo/`]
> **Interesting files from tree:** [list of relevant paths]
>
> **If API mode:** Fetch files with `gh api repos/<org>/<repo>/contents/<path>` or WebFetch on raw URLs.
> **If local mode:** Read files directly. Use Glob and Grep freely.
>
> **Write findings to:** `/tmp/heist-<timestamp>/research/config-scout.md` using the Write tool.
> **Return only a 2-4 line summary** listing the count and most notable items found.
>
> **What to find:**
>
> 1. **CLAUDE.md** — Read fully if present. Note structure, conventions, anything novel.
> 2. **Settings files** — Look for `settings.json`, `.claude/settings*`. Novel permission patterns, hook configs.
> 3. **Hooks** — Files in `hooks/` or `.claude/hooks/`. Record trigger and purpose.
> 4. **Other AI tool configs** — `GEMINI.md`, `CURSOR.md`, `.cursorrules`, `AGENTS.md`. Note novel patterns regardless of tool.
> 5. **Permission models** — How does this repo handle permissions? Look for `allowed-tools`, `permissions`, `allow` patterns.
> 6. **Installation/setup** — `install*`, `setup*`, `bootstrap*` files. How does this repo install itself?
>
> **Research file format:**
> ```
> # Config Scout — [repo name]
>
> ## Project Instructions (CLAUDE.md / similar)
> [Key conventions, novel sections, interesting approaches]
>
> ## Permission Model
> [How permissions are structured — novel patterns vs standard]
>
> ## Hooks
> [For each: trigger, purpose, implementation approach]
>
> ## Settings Patterns
> [Notable settings, model configs, feature flags]
>
> ## Installation Approach
> [How the repo installs/syncs — novel patterns]
> ```

---

## Scout C: Patterns Scout

**Prompt for Agent tool:**

> You are scanning a GitHub repo for novel engineering approaches, prompt techniques, and orchestration patterns.
>
> **Target repo:** `<org>/<repo>`
> **Browse mode:** [API | local clone at `/tmp/heist-<timestamp>/repo/`]
> **Interesting files from tree:** [list of relevant paths]
>
> **If API mode:** Fetch files with `gh api repos/<org>/<repo>/contents/<path>` or WebFetch on raw URLs.
> **If local mode:** Read files directly. Use Glob and Grep freely.
>
> **Write findings to:** `/tmp/heist-<timestamp>/research/patterns-scout.md` using the Write tool.
> **Return only a 2-4 line summary** listing the count and most notable items found.
>
> **What to find:**
>
> 1. **Subagent orchestration** — How does this repo coordinate multi-agent work? Look for `Agent`, `parallel`, `background` patterns.
> 2. **Prompt techniques** — Chain-of-thought instructions, persona definitions, guard rails, rationalization prevention, hard gates, red flags sections.
> 3. **Testing strategies** — How does this repo verify AI outputs? Look for `test`, `verify`, `check` patterns.
> 4. **Context management** — Patterns for managing context window: scratch directories, disk-write patterns, compaction, summaries.
> 5. **Novel workflows** — Interesting multi-step processes, pipelines, or decision flows.
> 6. **Templates** — Reusable templates for generating files.
>
> **Research file format:**
> ```
> # Patterns Scout — [repo name]
>
> ## Orchestration Patterns
> [Novel subagent, parallel work, or coordination approaches]
>
> ## Prompt Techniques
> [Interesting prompt engineering — personas, guard rails, gates]
>
> ## Testing & Verification
> [How AI work is verified]
>
> ## Context Management
> [How context window is managed]
>
> ## Novel Workflows
> [Interesting multi-step processes]
> ```
