"""Distribution and instruction regressions for Codex's actual host boundaries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


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
