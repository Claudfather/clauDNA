# Project Mission — clauDNA

## What this project is

clauDNA is the canonical set of skills, hooks, and agents for Claude Code, distributed as a marketplace plugin. Install it and any Claude Code instance gains a curated set of well-tested capabilities.

It's the "genome" of the Claudfather ecosystem — what every bot inherits at startup. Skills here are procedural (how to do X), not referential (what we know about X). Reference knowledge lives in Claudron, evaluation happens in Claudosseum, runtime is Claudlobby. clauDNA's job is just: ship the canonical capabilities, predictably, with version discipline.

## What it's becoming

A published Claude Code marketplace plugin sourced from arena-promoted champions. In the early phase the maintainer is the promotion engine; once Claudosseum's automation is trustworthy, promotions flow on a defined cadence. End state: any Claude Code user runs `/plugin install claudna@Claudfather` and gets a battle-tested skill set without thinking about provenance.

## North star

Materially smarter Claude Code with one install.

## Guiding principles

- **Curated quality over quantity.** Better to ship 30 skills that always work than 300 that mostly do.
- **Stability and predictability.** Users who pin to v0.4 should trust v0.4 behavior never changes. Breaking changes ship as new major versions.
- **Procedural content only.** If it's a how-to with a clear "when X, do Y" trigger, it belongs here. If it's reference material, it belongs in Claudron.
- **Marketplace-native distribution.** Plugin install is the only supported channel. Git clone is fine for development; production use goes through the marketplace.
- **Versioned, changelog'd, documented.** Every release ships with notes on what changed, what got promoted, what got demoted, and what users need to know.
- **No hosted dependencies for the user.** Installing clauDNA never requires an account or API key. The plugin is self-contained.

## Position in the ecosystem

**Consumes:** promotions from Claudosseum (champions ready to ship); manual additions during the early phase.

**Produces:** a marketplace plugin that Claudlobby bots install and any Claude Code user can install — the "what skills exist" answer for the entire ecosystem.

**Sibling boundaries:**
- clauDNA does not handle telemetry. Claudosseum does.
- clauDNA does not store reference knowledge. Claudron does.
- clauDNA does not run bots. Claudlobby does.
- clauDNA does not evaluate skills. Claudosseum does.

## In bounds for autonomous work

**Standing permissions:**
- Bug fixes in skill content (logic errors, broken examples, outdated references)
- Documentation, README, CHANGELOG entries
- Test additions and coverage improvements
- Reformatting to match marketplace plugin spec
- Skill metadata corrections (descriptions, argument hints, categorization)

**Current sprint focus:**
1. Restructure the repo to match Claude Code marketplace plugin requirements
2. Audit existing skills for v0.1 inclusion — promote keepers, archive the rest
3. Ship v0.1 of the marketplace plugin with manual curation
4. Define the release cadence and changelog format
5. Establish the input contract from Claudosseum: what does a "promoted skill" look like, and how does it land in clauDNA?

## Requires approval

- Adding a new skill to the canonical set (curated repo — additions are consequential)
- Removing or demoting an existing skill (disruptive for users on prior versions)
- Major version bumps and breaking changes
- Marketplace plugin metadata changes (name, description, author, scope)
- Changes to the input contract from Claudosseum
- Anything that introduces a hosted dependency for users

## Success metrics

- Marketplace plugin installs trending up over time
- Low rate of post-release demotions or hot-fixes (quality holding)
- Predictable release cadence (no months-long gaps, no lurching)
- Time from Claudosseum promotion to clauDNA release trending down as automation matures
- Community contributions of skill candidates (via Claudosseum) increasing

## What we choose not to build

- **Runtime skill distribution via MCP.** That was Claudosseum's old role. clauDNA is plugin-only.
- **A hosted dashboard or web UI.** clauDNA is files in a plugin. Discovery happens via the marketplace and the README.
- **Telemetry collection.** No phone-home. Telemetry lives in Claudosseum, opt-in.
- **Per-user customization.** clauDNA is the canonical set. Users wanting personalized skill sets layer their own atop, or run Claudosseum locally to produce their own promotions.
- **Skills that depend on hosted services.** A skill requiring third-party auth narrows the audience and adds fragility. Skills here should work standalone.
