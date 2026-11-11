"""Distribution and instruction regressions for Codex's actual host boundaries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def normalized(text):
    """Collapse Markdown wrapping so assertions bind clauses, not line breaks."""
    return ' '.join(text.split())


def test_every_selected_entrypoint_maps_tools_before_the_procedure():
    paths = json.loads(read('.codex-plugin/plugin.json'))['skills']
    for path in paths:
        body = read(path + '/SKILL.md').split('---', 2)[2]
        assert '../_shared/codex-tools.md' in body[:1000], path


def test_codex_dispatch_requires_real_same_host_controls_and_complete_role():
    text = read('skills/_shared/codex-tools.md')
    for requirement in ('TaskOutput', 'TaskStop', 'same execution host', 'complete',
                        'placeholders', 'unsupported', 'independent review', 'native CLI',
                        'absolute', 'allowed-tools', 'memory', 'background'):
        assert requirement in text


def test_codex_root_rule_rejects_unset_variables_and_other_host_cache():
    text = read('skills/_shared/claudna-root.md')
    assert 'Codex must not use the Claude cache fallback' in text
    assert 'actual absolute' in text
    assert 'quote' in text


def test_codex_simplification_uses_owned_changes_and_four_lenses():
    text = read('skills/_shared/subagent-prompts/simplify-codex.md')
    for lens in ('Reuse', 'Simplification', 'Efficiency', 'Altitude'):
        assert lens in text
    assert 'independent' in text
    assert 'owned' in text
    assert 'git reset --hard' not in text
    for path in ('skills/build/SKILL.md', 'skills/build-all/SKILL.md',
                 'skills/_shared/subagent-prompts/simplify-chain.md'):
        assert 'simplify-codex.md' in read(path), path


def test_selected_routes_do_not_require_the_excluded_scaffold_on_codex():
    for name in ('capture', 'using-claudna'):
        text = read(f'skills/{name}/SKILL.md')
        assert 'On Codex' in text
        assert 'source checkout' in text


def test_host_specific_memory_and_project_targets_are_explicit():
    assert 'On Codex' in read('skills/recall/SKILL.md')
    text = read('skills/init-project/SKILL.md')
    assert 'AGENTS.md' in text and 'preserve' in text
    assert 'CLAUDNA_STATE_DIR' in read('skills/audit/repo-health/repo-health.md')
    assert 'actual loaded' in read('agents/neon-analyst.md')


def test_project_agents_artifact_is_not_a_bundled_skill_reference(monkeypatch):
    import importlib.util
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location('integration', ROOT / 'scripts/integration-test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.extract_file_references('Create `AGENTS.md` from `references/AGENTS_MD_TEMPLATE.md`.') == [
        'references/AGENTS_MD_TEMPLATE.md']


def test_ironclad_checks_actual_dispatch_before_claiming_availability():
    text = read('skills/ironclad/SKILL.md')
    assert 'Subagents are always available' not in text
    assert '§14.1' in text and 'required independent review' in text


def test_health_retains_claude_dependencies_without_assigning_them_to_codex():
    health = read('skills/using-claudna/SKILL.md')
    dependencies = health.split('### 5. Dependencies', 1)[1].split('### 6.', 1)[0]
    assert 'On Claude Code' in dependencies and 'jq gh git node npx' in dependencies
    assert 'command -v' in dependencies
    assert 'On Codex' in dependencies and 'not universal Codex prerequisites' in dependencies


def test_health_retains_claude_telemetry_diagnostics_separate_from_codex():
    health = read('skills/using-claudna/SKILL.md')
    telemetry = health.split('### 6. Telemetry and continuity', 1)[1].split('### Results', 1)[0]
    for requirement in ('CLAUDNA_TELEMETRY_PATH', 'writability', 'size', 'line count', 'latest timestamp'):
        assert requirement in telemetry
    assert 'On Codex' in telemetry and 'unsupported' in telemetry
    assert 'Do not print raw events' in telemetry


def test_health_retains_claude_wired_matchers_and_scan_severity():
    text = read('skills/using-claudna/SKILL.md')
    claude_hooks = text.split('On Claude Code, inspect', 1)[1].split('### 4.', 1)[0]
    assert 'PostToolUseFailure' in claude_hooks and 'Write\\|Edit' in claude_hooks
    assert 'telemetry-emit' in claude_hooks and 'Skill' in claude_hooks
    assert '1–2' in text and '3+' in text


def test_resource_cleanup_selects_recorded_task_ownership_not_prefixes():
    for path in ('agents/neon-analyst.md', 'skills/neon/branch.md'):
        text = read(path)
        assert 'recorded branch ID' in text
        assert 'ownership' in text
        assert 'Never select' in text
        assert 'Always delete `claude/*`' not in text
        assert 'Always clean up `claude/*`' not in text
    worktree = read('skills/worktree/SKILL.md')
    assert 'only the exact worktrees this task created' in worktree
    assert 'omit branch deletion' in worktree


def test_artifact_routing_is_explicit_and_session_remains_chat_only():
    publish = read('skills/publish/SKILL.md')
    output = read('skills/_shared/output-guide.md')
    artifacts = normalized(publish.split('### Adapter: artifacts (explicit opt-in)', 1)[1].split(
        '### Adapter: vault', 1
    )[0])
    activation = normalized(output.split('### Activation', 1)[1].split('## 2. Common Requirements', 1)[0])
    output = normalized(output)
    assert 'only when the caller explicitly chooses `--to artifacts`' in artifacts
    assert 'explicitly selects `--output artifacts`' in artifacts
    assert 'It does not change any workflow default' in artifacts
    assert 'The `session` adapter remains chat-only and does not persist files.' in artifacts
    assert '`--output session`' in output and '`/claudna:publish --to session`' in output
    assert 'Print the doc body back into the chat, no persistence' in output
    assert 'explicit user-provided `--output artifacts` takes precedence over the `--auto` implied GitHub target' in output
    assert '`--auto` implies `--output github`' in output
    assert '`--output artifacts`' in activation
    # The pre-existing vault default is not a phase04 cutover.
    assert 'vault (default)' in publish


def test_artifact_publication_preserves_canonical_source_and_validates_selected_family():
    publish = read('skills/publish/SKILL.md')
    canonical_rule = normalized(publish.split('**Canonical artifact source rule:**', 1)[1].split(
        '### 1a.', 1
    )[0])
    pre_read = normalized(publish.split('**Before reading any source content**', 1)[1].split('### 1a.', 1)[0])
    family = normalized(publish.split('**Input and validation.**', 1)[1].split(
        '**Promotion of scratch output.**', 1
    )[0])
    promotion = normalized(publish.split('**Promotion of scratch output.**', 1)[1].split(
        '**Canonical export receipts.**', 1
    )[0])
    export = normalized(publish.split('**Canonical export receipts.**', 1)[1].split(
        'Native host receipts', 1
    )[0])
    assert 'validate that exact absolute path and owner' in pre_read
    assert 'including files individually selected from a family' in pre_read
    assert 'Missing, private, denied, stale, or otherwise uncertain validation means stop before content read' in pre_read
    assert 'family with exactly one `00_*.md` master and one or more `NN_*.md` phases' in family
    assert "all-or-nothing family validation" in family
    assert 'Non-markdown assets may be included only when explicitly selected as finished output.' in family
    assert 'content and frontmatter remain unchanged during later exports' in canonical_rule
    assert 'A failed or uncertain destination may be recorded only with its actual failed/unknown status, never as success.' in canonical_rule
    assert 'Session/chat output and dry-run remain mutation-free and create no receipt.' in canonical_rule
    assert 'Leave a selected source that is already canonical in place.' in promotion
    assert 'promote only the validated selected file/family and explicitly selected finished assets' in promotion
    assert 'hash each source' in promotion and 'verify final hashes' in promotion
    assert 'preserve each canonical source' in export
    assert 'resolve the current session\'s private receipt destination' in export
    assert 'recording each source path and content hash, destination, and actual returned result' in export
    assert 'Do not write a receipt during dry-run, session/chat output' in export


def test_workflow_artifact_paths_fail_closed_without_verified_native_identity():
    publish = read('skills/publish/SKILL.md')
    allocation = normalized(publish.split('**Identity and allocation.**', 1)[1].split(
        '**Input and validation.**', 1
    )[0])
    orchestration = read('skills/_shared/orchestration-guide.md')
    opt_in = normalized(orchestration.split('### Explicit artifacts opt-in', 1)[1].split(
        '### 1.1.', 1
    )[0])
    assert 'Obtain the current session ID and host from the qualified native runtime source.' in allocation
    assert 'Never infer identity from cwd, time, an operation ID, a filename, or a guessed value.' in allocation
    assert 'ordinary permission failure' in allocation
    assert 'stop the artifact write and report the reason' in allocation
    assert 'Do not fall back to an OS temp path' in allocation
    assert '--session "<verified-native-sid>" --host "<provider>" --kind artifacts --create' in allocation
    assert 'If identity is absent, conflicting, or unverified' in opt_in
    assert 'ordinary filesystem permission denies allocation' in opt_in
    assert 'do not fall back to `mktemp`' in opt_in
    assert '`--output session` remains chat-only and creates no files.' in opt_in


def test_plan_discovery_uses_explicit_sources_and_keeps_terminal_state_in_place():
    source = normalized(read('skills/_shared/source-guide.md'))
    explicit = normalized(source.split('### Explicit canonical plan artifacts', 1)[1].split(
        '### Lifecycle', 1
    )[0])
    build = normalized(read('skills/build/SKILL.md'))
    build_all = normalized(read('skills/build-all/SKILL.md'))
    forge = normalized(read('skills/forge/SKILL.md'))
    assert 'continuity artifact-path' in explicit and '--from-session' in explicit and '--path' in explicit
    assert 'Missing, private, ambiguous or unverifiable evidence stops selection.' in explicit
    assert 'Never select latest or scan other sessions.' in explicit
    assert 'uses its validated master and separately validates each selected phase path before' in explicit
    assert 'Canonical session artifacts become terminal in place' in explicit
    assert 'For an explicit canonical session artifact, first use the source guide' in build
    assert 'no latest-session selection or broad session scan' in build
    assert 'artifact path, terminal in place' in build
    assert 'Authorized plan status edits stay terminal in' in build_all
    assert 'Never select latest or derive the current identity from the input path.' in build_all
    assert 'inspect the current owner\'s selected plans or an explicit prior-session artifact' in forge
    assert 'never select latest or scan other session trees' in forge
