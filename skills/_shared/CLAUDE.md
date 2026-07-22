# skills/_shared/ — placement guidance

Shared orchestration material referenced by skills (no SKILL.md — nothing here is invocable;
consumers reference these files by disk path from skill bodies).

**What belongs here.** Contracts and guides shared by two or more skills: the orchestration
substrate, output/source routing, the Claudron consumer policy (`claudron-engine.md`), subagent
prompt templates, result-shape contracts.

**What must never land here.**

- **New SSOT text for another system's contract.** SSOTs live with their owner — Claudron's
  `SCHEMA.md` / `docs/CLI_CONTRACT.md` / `VAULT-STRUCTURE.md`; Claudlobby's fleet.yaml schema. A
  copy of owner text here must be a *rendered* copy carrying a CI drift gate —
  `output-guide.md` §3 is the precedent — never a hand-maintained fork. A consumer needing a
  contract change PRs the owner first.
- **Skill-specific content** — belongs in that skill's own directory.

**Placement test** (one line): if changing it correctly means PRing another repo first, it is
that repo's contract — point at it or render it with a gate; don't fork it. Full algorithm:
Claudron repo, `documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3.
