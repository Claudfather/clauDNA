# skills/ — placement guidance

Every directory here is one skill (the plugin auto-discovers; invoked `/claudna:<name>`). Binding
authoring rules live in [SKILL_CONTRACT.md](../SKILL_CONTRACT.md); this file is the boundary at
the seam — what belongs here, what must never land here.

**What belongs here.** Procedural content: method, workflow, and the rubrics/checklists that
version with the skill's method (its *closure*). Engineering-workflow behavior for any repo the
fleet works on.

**What must never land here.**

- **World-truth reference** — domain facts, schema tables, service inventories: anything that
  changes when the world changes rather than when your method changes. That is Claudron vault
  content: keep a pointer, or a rendered copy with a CI drift gate (the
  [`_shared/output-guide.md`](./_shared/output-guide.md) §3 pattern). The inverse door is already
  enforced: `/claudna:capture` rejects skill-shaped content from the vault.
- **Engine mechanics** — transport, dedup, index, ranking, schema. The `claudron` CLI is the
  door; this repo's consumer policy is [`_shared/claudron-engine.md`](./_shared/claudron-engine.md).
  New capability never lands on the frozen raw-tree fallback (its §4).
- **Fleet-operations behavior** — commands that operate bots or fleets rather than code belong in
  Claudlobby's `library/skills/`, whatever their file format.

**Placement test** (one line): *what must change in the same commit when this changes?* Your
method → here. The world or a sibling SSOT → vault note or rendered copy. The fleet runtime →
Claudlobby. Full algorithm: Claudron repo,
`documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3.
