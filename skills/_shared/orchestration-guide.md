# Shared Orchestration Guide

Shared reference for skills that use subagent orchestration to produce design documents. This file is not a skill — it has no `SKILL.md` and does not appear in skill listings. Skills reference it by telling subagents to read it from disk at `skills/_shared/orchestration-guide.md`.

---

## 1. Scratch Directory

At orchestration start, define a scratch directory path for this session:

```
/tmp/<skill-name>-<timestamp>/research/
```

- `<skill-name>` is the slash command name (e.g., `product-enhance`, `audit`)
- `<timestamp>` is `YYYY-MM-DD_HHMMSS`
- Research subagents write research files here (use `general-purpose` subagents — Explore agents lack the Write tool)
- Plan agents read research from here

Example: `/tmp/product-enhance-2026-02-17_143022/research/`

**Permissions note:** Do NOT use Bash `mkdir` to create this directory. The Write tool creates parent directories automatically. The first subagent's Write call to this path will create the directory. This avoids any Bash permission prompts — the entire disk-write workflow uses only Read and Write tools, which are blanket-allowed via the `claude-workflow` permission category.

**Subagent type note:** Explore agents (`subagent_type: "Explore"`) do NOT have the Write tool — they are read-only. For the disk-write pattern, use `general-purpose` subagents (`subagent_type: "general-purpose"`) which have access to all tools including Write. Use Explore agents only when you need fast, read-only codebase searches that don't need to persist results to disk.

---

## 2. Research Agent → Disk Pattern

Research subagents (`general-purpose` type) write structured research to disk and return only a short summary to the orchestrator.

### What research agents write to disk

Each research subagent writes a research file to:

```
/tmp/<skill-name>-<timestamp>/research/<slug>.md
```

Research file template:

```markdown
# <Research Topic>

## Summary
<2-3 sentence overview of findings>

## Affected Files
- `path/to/file.ext:line` — description of what's here
- `path/to/file.ext:line` — description of what's here

## Findings
<Detailed analysis, evidence, code snippets with file:line references, root causes>

## Severity
<Assessment relevant to the skill's domain — e.g., CRITICAL/HIGH/MEDIUM/LOW>
```

### What research agents return to the orchestrator

Return ONLY a 2-4 line summary. Example:

```
Scanned authentication flow. Found 3 issues:
- JWT secret hardcoded (src/auth.ts:12) — CRITICAL
- No rate limiting on login endpoint — HIGH
- Session cookies missing secure flag — MEDIUM
Full research: /tmp/audit-2026-02-17_143022/research/auth-flow.md
```

**The orchestrator MUST NOT read the full research files into its context.** The orchestrator uses these summaries for user-facing presentation tables only.

---

## 3. Plan Agent → Disk Pattern

Plan agents read research from disk, read this guide for quality standards, and write final docs into the session's **scratch docs directory** (`/tmp/<skill>-<timestamp>/docs/`). The orchestrator then publishes the finished family in one call — placement into `documentation/` is `/claudna:publish`'s job, never the agents' and never the orchestrator's own Write calls.

### Launch prompt template for Plan agents

The orchestrator constructs a prompt for each Plan agent that includes:

```
## Setup

1. Read skills/_shared/planning-standard.md — follow the Quality
   Standard and Phase Doc Structure exactly (docs are publishable docs:
   output-guide §3 frontmatter + the §4.1 body skeleton; the standard's
   content sections map onto it — see its mapping table).
2. Read the research file(s) at: /tmp/<skill>-<timestamp>/research/<slug>.md
3. [Any skill-specific quality requirements, inlined by the calling skill]

## Task

Write a phase document for: <enhancement title>
Output path: /tmp/<skill>-<timestamp>/docs/<NN>_<slug>.md

## When done

Return ONLY a metadata summary in this format:
- Wrote: <output file path>
- PR title: <concise title>
- Effort: <Low/Medium/High> (<estimate>)
- Risk: <Low/Medium/High>
- Files modified: N | Files created: N
- Dependencies: <phase numbers or "None">
- Unlocks: <phase numbers or "None">

Do NOT return the full document content.
```

### Publishing the family (orchestrator step)

After all Plan agents complete, the **orchestrator composes the `00_` master** from the Plan agents' metadata summaries and writes it to the same scratch docs directory — the sole exception to "never write docs" (§6's read-the-first-15-20-lines allowance exists for exactly this), with output-guide §3 frontmatter like every family member. Then it places the family with one call:

```
/claudna:publish /tmp/<skill>-<timestamp>/docs/ --to docs --dir documentation/planning/<subdirectory>/<session_name>_<YYYY-MM-DD>/
```

Family mode validates each doc — `NN_*` phase docs against the full §4.1 skeleton, the `00_*` master under the presence-only exemption — and writes nothing on any failure (see `skills/publish/SKILL.md` Step 1b / the docs adapter). The `--dir` value comes from the registry in `skills/_shared/documentation-standard.md` §2.

### What the orchestrator MUST NOT do

- **MUST NOT write docs itself** — it does not have the research context or quality standards to produce adequate output. Always delegate to Plan subagents. (Sole exception: the `00_` master, composed from metadata summaries — above.)
- **MUST NOT write into `documentation/` directly** — placement goes through `/claudna:publish --to docs` (family mode), the single writer for that plane.
- **MUST NOT collect full doc content** from Plan agents into its context.
- **MUST NOT read finished docs** into its context (except the first 15-20 lines for header metadata if needed for the overview doc).

---

## 4. Quality Standards

See `skills/_shared/planning-standard.md` for the full quality standard. All plan output — phase docs, master docs, GitHub Issue bodies — must meet this standard.

Plan agents must read `planning-standard.md` from disk alongside this guide.

---

## 5. Phase Doc Structure

See `skills/_shared/planning-standard.md` for the required phase doc structure (9 mandatory sections). Skills with domain-specific sections specify those in their own SKILL.md — they layer on top of the shared structure.

---

## 6. Context Window Management

The orchestrator session is long-running and must stay within context limits. These rules prevent context blow-up:

### Launching Plan agents

- Launch ALL Plan agents in parallel using `run_in_background: true`
- Each Plan agent writes its output to the scratch docs directory via the Write tool
- Collect Plan agent completions via TaskOutput one at a time
- Each TaskOutput response contains only the metadata summary (not the full doc)
- After all agents complete, present the summary table to the user

### What NEVER enters orchestrator context

- Full research files from research subagents (they stay on disk)
- Full phase/remediation docs from Plan agents (they stay on disk)
- If the orchestrator needs to verify a doc was written correctly, read only the first 15-20 lines (the header/metadata section)

### Sequential collection pattern

Even with the disk-write pattern, collect agent completions ONE AT A TIME:

1. Launch all Plan agents in parallel with `run_in_background: true`
2. Collect agent 1 completion via TaskOutput (receives metadata only)
3. Collect agent 2 completion via TaskOutput (receives metadata only)
4. Repeat for each agent — one at a time, sequentially
5. Never collect multiple agent outputs in the same message

---

## 7. Permissions & Tool Usage

The disk-write workflow is designed to use **only Read and Write tools** for all file I/O — no Bash commands. This means:

- **No `mkdir` calls** — Write tool creates parent directories automatically
- **No `cp` or `mv` calls** — all file creation goes through the Write tool
- **No `cat` or `head`/`tail` calls** — all file reading goes through the Read tool (use `limit` and `offset` parameters for partial reads)
- **No `find` calls** — use the Glob tool for file discovery by pattern
- **No `grep` calls** — use the Grep tool for content search (supports regex, glob filters, output modes, and `head_limit`)

Both Read and Write are blanket-allowed via the `claude-workflow` permission category (default in clauDNA). This means:

- Research subagents writing research to `/tmp/` → **no permission prompt**
- Plan agents reading research from `/tmp/` → **no permission prompt**
- Plan agents reading this guide from `skills/_shared/` → **no permission prompt**
- Plan agents writing docs to the scratch docs directory (`/tmp/…/docs/`) → **no permission prompt**
- `/claudna:publish --to docs` placing the family under `documentation/planning/` (Read/Write tools) → **no permission prompt**

Subagents launched via the Task tool inherit the parent session's permissions. No additional permission grants are needed.

### Shell operator restriction

Shell operators (`&&`, `||`, `;`, `|`, `2>&1`) in Bash commands break `allowed-tools` permission pattern matching. A command like `source venv/bin/activate && pytest` cannot match any wildcard pattern — the user gets prompted for manual approval on every invocation.

Rules for all skills:
- **Never chain commands with `&&` or `;`.** Make separate parallel Bash tool calls instead.
- **Never pipe output with `|`.** Run the command bare and read the result.
- **For Python virtual environments:** Use the venv's python directly — `./venv/bin/python -m pytest` not `source venv/bin/activate && pytest`.
- **For `cd`:** Use absolute paths — `python /path/to/app.py` not `cd /path/to && python app.py`.

**No exceptions.** Previous versions of this guide listed `source .env &&` and `cd <worktree> &&` as accepted. Both have clean alternatives — see below.

### Environment variables from `.env`

Skills that need credentials or config from `.env` must NOT use `source .env && command`. Instead:

1. **Read** `.env` (and `.env.local` if it exists) using the Read tool
2. **Discover** the needed variable — don't hardcode a specific name. For database URLs, look for `DATABASE_URL`, `NEON_PROD_URL`, `POSTGRES_URL`, `PG_URL`, etc. For API keys, look for common patterns.
3. **Pass the value inline** in the command: `psql "postgres://discovered-url" -c "SELECT 1"`

This eliminates the `&&` operator AND makes skills portable across projects that use different variable names.

### Working directory for worktrees/subagents

`cd` persists between Bash calls within a session. Run `cd /path/to/worktree` as the first Bash call, then all subsequent commands run from that directory. No `cd <path> && command` chaining needed.

For Python virtual environments, use the venv binary directly: `./venv/bin/python -m pytest` — never `source venv/bin/activate && pytest`.

### Redacting credentials in CLI output

Never quote raw infra/CLI output that could contain a credential into a finding, a report, or a returned summary. Prose masking ("show `sk-****`") has leaked live tokens — a Telegram bot token, then a neon API key — because it relied on the model remembering to mask and only illustrated the `sk-` shape.

Scrub deterministically with the bundled redactor at `scripts/redact.py` (`${CLAUDE_PLUGIN_ROOT}/scripts/redact.py`, or the highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/scripts/redact.py` when that variable is unset). The disk-write pattern (§2) already writes findings to disk, so scrub the file **in place** — a bare command, no pipe (per the shell-operator restriction above):

```bash
python3 "<redactor>" <findings-file>
```

Run it over any research or findings file that captured command output before that file is returned or published. The redactor masks Telegram / OpenAI / GitHub / AWS / Slack / Google / neon key shapes, `SECRET=value` assignments, and high-entropy tokens, and leaves git SHAs, UUIDs, and `file:line` references intact. It is idempotent — a redundant pass is harmless.

---

## 8. Archive Convention

Output directories follow this pattern per skill (reached via `publish --to docs --dir` — the registry in `skills/_shared/documentation-standard.md` §2; skills never *place finished docs* here directly. Documented exceptions: `/claudna:implement-plan`'s status-marker write-backs and its `git mv` archive move):

```
documentation/planning/<subdirectory>/<session_name>_<YYYY-MM-DD>/
```

Where `<subdirectory>` varies by skill or audit lens:
- product-enhance, product-vision, `audit design`: `phases/`
- `audit frontend-perf`: `performance/`
- `audit security`: `security/`
- `audit tech-debt`: `tech_debt/`

When all phases are complete, the session directory moves to:

```
documentation/archive/<session_name>_<YYYY-MM-DD>/
```

via `git mv`. This is handled by `/claudna:implement-plan` — planning skills only generate plans, never archive them.

---

## 9. Subagent Workflow Reference for Skills

When a skill's doc generation step (typically the final step) delegates to Plan subagents, include this reference instead of inlining the full workflow:

> **Follow the subagent workflow defined in the orchestration guide (`skills/_shared/orchestration-guide.md`):**
> - Plan Agent → Disk pattern (Section 3)
> - Quality standards and phase doc structure (`skills/_shared/planning-standard.md`)
> - Context window management (Section 6)
> - Archive convention (Section 8)
> - Pre-handoff adversarial review (`skills/_shared/pre-handoff-checklist.md`)
>
> Plan agents read research from the session's scratch directory, write docs into the scratch docs directory (the orchestrator publishes the family via `/claudna:publish --to docs` — §3), and return only a metadata summary.
>
> **The orchestrator MUST NOT write docs itself.** Always delegate to Plan subagents.

Skills that have domain-specific quality requirements or custom phase doc sections should specify those AFTER this reference block. The shared standards always apply; skill-specific additions layer on top.

### Alternative Output Targets

Skills support `--output github` and `--output session` in addition to the default `docs` target. When `--output github` is active, the skill runs the full analysis and plan generation pipeline (no phases are skipped), then writes output as GitHub Issues instead of planning docs. When `--output session` is active, findings are presented in chat only with no persistence.

Follow the output guide at `skills/_shared/output-guide.md` for target-specific formatting, deduplication, labels, and subagent workflow details.

---

## 10. Autonomous Mode (`--auto`)

Planning skills that support `--auto` can run fully non-interactively — no user gates, no questions, no confirmations. This enables rolling automated audits, scheduled reviews, and headless operation.

### What `--auto` means

When `$ARGUMENTS` contains `--auto`:

1. **Implies `--output github`.** Findings always go to GitHub Issues, never to planning docs. The planning doc workflow requires user decisions (session naming, scope confirmation, selection) that can't happen without a human.
2. **Skip all user gates.** Do not ask for confirmation, scope selection, or approval. Proceed with sensible defaults.
3. **Scope from arguments.** The focus area must come from `$ARGUMENTS` (e.g., a directory path). If no scope is provided, scan the full codebase but limit findings to the top 10 most impactful.
4. **No Plan Mode.** Skip `EnterPlanMode`/`ExitPlanMode` — there's no deliberation phase when running autonomously. Go straight to scan → findings → issues.
5. **Bail gracefully.** If the skill genuinely cannot proceed without user input (e.g., deployed URL required for the audit engine's design lens), write what you have to the handoff file and stop. Do not block.

### Default behavior changes with `--auto`

| Interactive (default) | `--auto` |
|---|---|
| Ask user for scope | Use scope from `$ARGUMENTS`, or full codebase |
| Present findings, wait for confirmation | Create issues immediately |
| Ask which findings to act on | Act on all findings above LOW severity |
| Write planning docs (`--output docs`) | Create GitHub Issues (`--output github`) |
| Multiple user gates between phases | Zero interaction |

### How skills should reference this

Skills that support `--auto` should add to their Arguments section:

```
- `--auto`: Fully non-interactive. Implies `--output github`. Scans, creates issues, returns summary. See orchestration guide Section 10.
```

And at the end of their procedure, add an "Autonomous Mode" section:

```
## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip [specific user gates in this skill]
2. [Any skill-specific auto defaults]
3. Create GitHub Issues per the output guide (`--output github`)
4. Return structured summary for audit tracking
```

### For implementation skills (Tier 3)

The rules above describe planning skills that produce GitHub Issues. Implementation skills (Tier 3 per §13: `/claudna:implement-plan`, and any future skill that produces PRs from existing plans) follow a parallel `--auto` contract with these differences:

- **Implies producing a PR, not an issue.** Does NOT imply `--output github`. The terminal artifact is an open PR on the work item's source branch.
- **Never merges.** The merge gate is unconditionally skipped in `--auto`. A human ratifies the PR.
- **Requires a target work item.** `--auto` MUST be invoked with `--source github <#>` or an explicit plan path. Picker / browse modes are disallowed.
- **Trusts the caller has vetted the plan.** Interactive challenge rounds are replaced by either (a) trust (the upstream planning skill ran adversarial-review at creation time per §5.3 of the design) or (b) machine synthesis via `/claudna:weigh-development-paths --auto` per design §5.5.2. The skill does not stop to ask the user.
- **"Feels wrong" exits with `outcome: blocked`** with a populated `blocker_description` field, instead of stopping for user discussion.
- **Emits the structured result shape (§10.C below)** at the end of the run.

Skills MUST add to their Arguments section:

```
- `--auto`: Fully non-interactive mode. Required target work item via `--source github <#>` or explicit plan path. Never merges. See orchestration guide §10 (Tier-3 sub-section).
```

And add an "Autonomous Mode (--auto)" section at the end of their procedure mirroring planning-skill structure but documenting the Tier-3 specifics.

### Structured Result Shape

Every `--auto` run emits a single fenced JSON block as its final output (the last content before the run ends). The orchestrator (e.g., claudlobby's `autonomous-runner` skill) parses this block. Skills must NOT print anything after it.

```json
{
  "skill": "<skill name, e.g. 'implement-plan'>",
  "outcome": "completed | bypassed | needs-input | blocked | partial",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123"],
    "pr_url": "https://github.com/org/repo/pull/456",
    "files_changed": 3,
    "lines_added": 47,
    "lines_removed": 12,
    "branch": "implement/some-slug"
  },
  "summary": "<2-4 line human-readable summary for Telegram report-back>",
  "next": "<orchestrator hint for what to schedule next, or null>",
  "errors": [],
  "blocker_description": null
}
```

#### Field rules

- `skill` (required): the skill's name as it appears in frontmatter.
- `outcome` (required): exactly one of the five values listed. Skills MUST NOT invent new outcome strings.
- `artifacts` (required): an object. Keys are skill-dependent — planning skills include `issues_created`; implementation skills include `pr_url`. Both are optional fields within `artifacts`. Skills SHOULD include `files_changed`, `lines_added`, `lines_removed`, `branch` when they touch code.
- `summary` (required): 2-4 lines of plain text. No markdown. For Telegram report-back.
- `next` (optional, may be null): a one-sentence hint for the orchestrator.
- `errors` (required, may be empty): array of strings describing non-fatal issues encountered during the run.
- `blocker_description` (required when outcome is `blocked` or `needs-input`, null otherwise): one or two sentences explaining what blocks the work and what would unblock it.

#### Outcome semantics

| Outcome | Meaning | Retry safe? |
|---|---|---|
| `completed` | Work landed; PR or issues exist as expected. | n/a (don't retry) |
| `bypassed` | Explicit decision not to work this item (heavy-refactor tripwire, scope-exceeded). | No — needs policy change |
| `needs-input` | Cannot proceed without a human decision (ambiguous design, conflicting plans). A comment was posted on the source. | No — needs human action first |
| `blocked` | Attempted work but couldn't complete due to environment failure or unresolved internal contradiction. | Yes in principle, but treat as suspect until investigated |
| `partial` | Some progress made, but not the full outcome. | Yes — followup needed |

#### Emission rules

- The JSON block MUST be the final output of the `--auto` run. No text after.
- The JSON block MUST be valid (parseable by `json.loads`).
- The block MUST be fenced with ```` ```json ```` (the language hint matters — orchestrators key off it).
- The skill SHOULD log the block to stdout, not to a side-channel.

### Skills that support `--auto`

| Skill | Auto-viable? | Notes |
|---|---|---|
| `/claudna:audit tech-debt` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:audit security` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:product-enhance` | ✅ Yes | Uses triage path (skip discovery/interview) |
| `/claudna:audit frontend-perf` | ✅ Yes | Requires page/flow in arguments |
| `/claudna:audit docs` | ✅ Yes | Global review mode, auto-fix stale docs |
| `/claudna:audit access-path` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:product-vision` | ⚠️ Limited | Vision without user input produces generic ideas. Use only with tight scope. |
| `/claudna:audit design` | ❌ No | Requires screenshots, deployed URL, visual judgment |
| `/claudna:session` (handoff/resume/checkpoint modes) | ✅ Yes | Already implemented |
| `/claudna:implement-plan` | ✅ Yes | **Tier 3.** Phase 3 of the autonomous-mode rollout. Consumes plans/issues, produces PRs, never merges. |
| `/claudna:weigh-development-paths` | ✅ Yes | **Composable.** Phase 1 adds `--auto` for chained use from `/implement-plan --auto`. Returns refined plan. |
| `/claudna:adversarial-review` | ✅ Yes | **Composable.** `--dispatch` mode is non-interactive when invoked from another skill. Returns structured critique findings. |

---

## 11. Shared Skill Reminders

The following rules apply to ALL orchestration skills. Skills should reference this section rather than restating these individually:

- **One PR per doc.** Each phase/remediation/fix doc maps to exactly one PR when implemented via `/claudna:implement-plan`.
- **This skill produces plans, not code.** Implementation is always handled by `/claudna:implement-plan`, which provides its own challenge round, verification, and PR workflow. Do NOT build, branch, or create PRs from planning skills.
- **Testing is non-negotiable.** Every phase doc must include a test plan. Implementations without tests are incomplete.
- **Documentation is non-negotiable.** Every phase doc must specify documentation updates. Code without docs is incomplete.
- **Respect existing architecture.** Enhancements and fixes should work *with* the system's existing patterns, not introduce alien abstractions.

---

## 12. Context Efficiency — Why These Patterns Work

Reference for skill authors. Understanding the "why" helps you make good decisions in situations these patterns don't explicitly cover.

### Prefix caching

The API caches the prompt by prefix — everything from the start of the request to each breakpoint. Order matters: **static content first, dynamic content last.** The actual order is: system prompt & tool definitions (globally cached) → CLAUDE.md (cached per-project) → session context (cached per-session) → conversation messages. Every pattern in this guide preserves that prefix.

### Model stability

Prompt caches are per-model. Switching models mid-session rebuilds the entire cache. Subagents launched via Task inherit the parent model automatically — this is correct behavior. Never recommend `/model` mid-session. If different-model work is needed, use a Task subagent (separate cache).

### Tool set stability

Tool definitions are part of the cached prefix. Adding or removing tools mid-session invalidates the cache for the entire conversation. Use `EnterPlanMode`/`ExitPlanMode` as tools (not tool swapping). For MCP tools, use `defer_loading: true` stubs — full schemas load on demand via `ToolSearch`.

### Compaction awareness

Long orchestration sessions can trigger compaction (automatic context summarization). The disk-write pattern defends against this: research and docs stay on disk, so the orchestrator context stays lean. Rules:
- Orchestrator must not read full research files or finished docs into its context.
- Research subagents return 2-4 line summaries; Plan agents return metadata only.
- If you need to verify a doc, read only the first 15-20 lines (header/metadata).

### Redundant reads

CLAUDE.md and MEMORY.md are already in the system prompt — the orchestrator must NOT re-read them. Subagents (Task tool) run in separate sessions and do NOT inherit the parent's system prompt content, so they DO need to read shared references from disk (e.g., this guide, CLAUDE.md if relevant).

---

## 13. Skill Priority Ordering

When multiple skills could apply to a task, invoke them in tier order. Process skills determine HOW to approach a problem. Planning skills determine WHAT to build. Implementation skills execute. Deployment skills ship. Skipping tiers leads to building the wrong thing or shipping unverified work.

### Priority tiers

| Tier | Category | Skills | Purpose |
|------|----------|--------|---------|
| 1 | **Process** | investigate-app, verify-completion | Establish approach, verify assumptions, gather evidence, debug |
| 2 | **Planning** | product-enhance, product-vision, audit (lens engine — lenses per `audit-lens-contract.md`) | Analyze what to build, identify gaps, produce design docs |
| 3 | **Implementation** | implement-plan, review-work (mode engine — changes/pr/multi-pr), quick-commit, commit-push-pr | Execute plans, review code, commit and ship PRs |
| 4 | **Deployment & Ops** | modal, railway, vercel, neon, dbt (infra engines — verb modes per `infra-cli-contract.md`) | Deploy, monitor, query infrastructure |

**Utility skills** (session, capture, recall, claudron, find-skills, worktree, using-claudna) are not tiered -- they are invoked on demand for session management, not as part of a build workflow. (The former docs-review and repo-health utilities are now `docs` and `repo-health` lenses of the tiered `audit` engine.)

### Rules

- **Higher tiers first.** When a task could benefit from skills in multiple tiers, start with the lowest-numbered tier. Example: a bug report should invoke investigate-app (Tier 1) before implement-plan (Tier 3).
- **Within a tier, order does not matter.** Tier 1 skills can run in any order relative to each other.
- **Skipping tiers is allowed when inapplicable.** Not every task needs all four tiers. A simple deploy needs only Tier 4. A code review needs only Tier 3. The rule is: do not skip a tier that IS applicable.
