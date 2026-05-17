---
name: skill-scaffold
user-invocable: true
description: "Use when you want to scaffold a new clauDNA skill directory with correct structure, valid frontmatter, and a starter body that passes validation."
argument-hint: "[skill-name]"
allowed-tools:
  - Bash(python3 *)
  - Bash(ls *)
  - Bash(mkdir *)
  - Read
  - Write
  - Glob
---

# Skill Scaffold — Interactive Skill Wizard

Scaffold a new skill directory with valid SKILL.md frontmatter and body skeleton. Generates boilerplate that passes `validate-skills.py` out of the box so contributors can focus on writing the procedure.

## Procedure

### Step 1: Gather Inputs

If the user provided a skill name as an argument, use it. Otherwise prompt for the following:

1. **Skill name** — must be `kebab-case` (lowercase letters, digits, hyphens only). This becomes both the directory name and the `name:` frontmatter field.
2. **One-line description** — must start with "Use when" and be 20-500 characters. This becomes the `description:` frontmatter field.
3. **Tool requirements** — which tools does the skill need? Common patterns:
   - Read-only analysis: `Read, Grep, Glob`
   - Code modification: `Read, Write, Edit, Grep, Glob, Bash(git *)`
   - GitHub interaction: `Bash(gh *), Bash(git *), Read, Grep, Glob`
   - Full orchestration: `Read, Write, Edit, Grep, Glob, Bash(git *), Bash(gh *), Agent`
   - None (uses only defaults): omit the field
4. **Argument hint** — does the skill accept arguments? If yes, what format? (e.g. `[--flag] [positional]`)
5. **Uses subagents?** — will the skill delegate to Agent/subagents for parallel work?
6. **External CLI dependencies** — does it need tools beyond git/curl/jq? (e.g. `gh>=2.0`, `vercel`, `neonctl`)

### Step 2: Validate Inputs

Before creating anything:

- Confirm `skills/<name>/` does **not** already exist. If it does, stop and tell the user:
  ```
  Error: skills/<name>/ already exists. Choose a different name or edit the existing skill.
  ```
- Confirm the name matches `^[a-z][a-z0-9-]*$` (starts with letter, kebab-case).
- Confirm description starts with "Use when" and is 20-500 characters.

### Step 3: Create Skill Directory and SKILL.md

Create `skills/<name>/SKILL.md` with the following structure:

```markdown
---
name: <name>
user-invocable: true
description: "<description>"
[argument-hint: "<hint>"]       # only if provided
[allowed-tools:]                # only if tools were specified
[  - <tool>]
[requires:]                     # only if external CLI deps declared
[  - cli: "<tool>"]
[    reason: "<why>"]
---

# <Title Case Name>

<One-line restatement of what the skill does.>

## Procedure

### Step 1: <First Action>

1. <Placeholder — describe what to do>
2. <Placeholder — describe what to check>

### Step 2: <Second Action>

1. <Placeholder — describe what to do>
2. <Placeholder — describe what to check>

### Step 3: Verify & Report

1. Confirm the output is correct
2. Present results to the user
```

**If subagents indicated**, also create `skills/<name>/subagent-prompts.md`:

```markdown
# Subagent Prompts — <name>

Reference material for subagent prompts used by this skill.

## Scout Agent

```
<Prompt template for scout/research subagent>
```

## Worker Agent

```
<Prompt template for implementation subagent>
```
```

### Step 4: Run Validator

Run:

```bash
python3 scripts/validate-skills.py
```

If the new skill fails validation, read the error, fix the generated file, and re-run until it passes.

### Step 5: Present Result

Print a summary:

```
Skill Scaffolded
═══════════════════════════════════════════════════════
  Created:
    skills/<name>/SKILL.md          (frontmatter + skeleton)
    [skills/<name>/subagent-prompts.md]  (if subagents)

  Next steps:
    1. Edit the procedure steps in skills/<name>/SKILL.md
    2. Test locally: claude --plugin-dir /path/to/clauDNA
    3. Run validator: python3 scripts/validate-skills.py
    4. Submit PR referencing any tracking issue
═══════════════════════════════════════════════════════
```

## Rules

- **Never overwrite an existing skill directory.** If `skills/<name>/` exists, refuse and explain.
- **Generated output must pass validation on first run.** If it doesn't, that's a bug in the scaffold — fix it before presenting to the user.
- **Follow SKILL_CONTRACT.md exactly.** The scaffold is the happy path for contributors — if it produces invalid output, trust erodes.
- **Kebab-case only.** Reject camelCase, PascalCase, snake_case, or names with spaces.
- **Description must start with "Use when".** This is a SKILL_CONTRACT convention. Enforce it at input time, not after generation.
