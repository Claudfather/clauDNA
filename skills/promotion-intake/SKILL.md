---
name: promotion-intake
user-invocable: true
description: "Use when a Claudosseum promotion package (manifest + battle history + telemetry + SKILL.md bundle) is ready to land in clauDNA — validates it against the promotion contract and stages the skill as a reviewable PR. Not for authoring new skills by hand; use /claudna:skill-scaffold for those."
argument-hint: "<package-path-or-url> [--dry-run] [--auto]"
requires:
  - cli: gh
    reason: "Fetching remote packages and the PR step (via /claudna:ship)"
---

# Promotion Intake

The importer half of the Claudosseum→clauDNA promotion contract: consume a promotion package, validate it with the contract's own enforcer (`scripts/validate-promotion-package.py`), and — only on a clean pass — stage the promoted skill as a PR for maintainer review. This skill makes the mission's "promotions flow on a defined cadence" mechanically real; the maintainer's admin-merge stays the final gate.

Versioning is out of scope: no `plugin.json` bump, no CHANGELOG version cut — release trains are separate.

## Arguments

- `<package>` — path to a promotion package directory, or a URL to fetch one (a directory bundle containing `manifest.json`, `battle-history.json`, `telemetry-summary.json`, `SKILL.md`, and any support files).
- `--dry-run` — validate and report exactly what would be staged; write nothing, open nothing.
- `--auto` — non-interactive (Claudosseum's automation calls this): no questions, and a §10.C structured result as the final output.

## Procedure

### 1. Acquire the package

- Local path → use it directly.
- URL → fetch into the scratch directory (`gh repo clone`/`gh release download`/`curl` per the URL's shape), then treat as a local path.
- Not found / unreadable → **blocked** (§5).

### 2. Validate against the promotion contract

```bash
python3 scripts/validate-promotion-package.py <package-dir> --json
```

The validator is the single source of truth for the contract — arena thresholds, judge confidence, telemetry thresholds, manifest schema, content-hash match, SKILL_CONTRACT conformance, name collision. This skill never re-implements any of its rules.

- **Exit 0** → proceed.
- **Exit non-zero** → **blocked** (§5): every `[FAIL]` check goes into `errors[]` verbatim; `blocker_description` names the first failing check and what threshold or hash didn't match. Do not "fix up" a failing package — the fix belongs upstream in Claudosseum.

### 3. Stage the promotion (skipped under `--dry-run`)

On a new branch `promote/<skill-name>`:

1. Copy the package's `SKILL.md` and support files (everything except the three package-metadata JSON files) to `skills/<name>/` — byte-identical: the validator's content-hash check binds the arena-tested content to what lands.
2. Append a CHANGELOG entry under `## [Unreleased]` / `### Added`: skill name, one-line description, and the provenance line `Promoted from the Claudosseum arena (package manifest <manifest-version>, win rate <rate>, <n> battles).` drawn from the manifest.
3. Re-run the repo gates locally: `python3 scripts/validate-skills.py` and `python3 -m pytest tests/ -q` must both pass with the new skill in place. A failure here (e.g. a routing-fixture or reference-integrity conflict the package validator can't see) → **blocked**, with the gate output in `errors[]`.

**Interactive mode:** present the staging summary (files, CHANGELOG entry, validator output) and ask once: "Open the promotion PR? (y/n)". **`--auto`:** proceed without asking — the PR itself is the human gate.

### 4. Open the PR

Invoke `/claudna:ship` with:
- Title: `feat: promote /claudna:<name> from Claudosseum arena`
- Body: the validator's check table, the manifest's provenance block (win rate, battles, judge confidence, telemetry period), and the staged-file list.

CI re-runs every gate; the maintainer reviews and merges. This skill never merges.

### 5. Structured result (`--auto`)

Emit the §10.C structured result per `skills/_shared/orchestration-guide.md` as the final output — nothing after it:

```json
{
  "skill": "promotion-intake",
  "outcome": "completed",
  "artifacts": {
    "package": "<path-or-url>",
    "skill_name": "<name>",
    "validation": "pass",
    "pr_url": "<URL from ship, or null for --dry-run>",
    "dry_run": false
  },
  "summary": "Promotion staged: /claudna:<name> — PR <url>.",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

Outcomes: `completed` — PR opened (or dry-run validated clean; `pr_url: null`, `dry_run: true`). `blocked` — acquisition, contract validation, or repo-gate failure; `errors[]` carries the verbatim failures, `blocker_description` the first cause. There is no `partial`: a promotion either stages whole or not at all.

## Rules

- **The validator is law.** Never land content the validator rejected; never edit package content to make it pass.
- **Byte-identical staging.** The content hash binds arena-tested content to what ships.
- **One skill per package, one PR per promotion.**
- **Never merges, never bumps versions.** The maintainer's review is the cadence's human gate.
