"""Codex catalog choices are not native automatic-routing measurements."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import routing_eval_codex as evaluator


@pytest.fixture(autouse=True)
def private_store_root(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDNA_STATE_DIR', str(tmp_path / 'relocated state root'))


def test_floor_covers_every_selected_skill_and_preserves_source_rows():
    report = evaluator.floor()
    assert report['method'] == 'catalog_selection'
    assert report['selected'] == 37
    assert report['source_rows'] == 42
    assert report['controls'] == 2
    assert report['positive_coverage'] == 37
    assert report['unsupported'] == [{'skill': 'promotion-intake', 'reason': 'requires repo-clone context'}]
    assert report['live_cases'] == 18
    assert report['errors'] == []


@pytest.mark.parametrize(('value', 'error'), [
    ('not-json', 'invalid_json'),
    ('{"skill":"review-work","mode":null}', 'wrong_mode'),
    ('{"skill":"capture","mode":"changes"}', 'wrong_skill'),
    ('{"skill":"skill-scaffold","mode":null}', 'excluded_skill'),
    ('{"skill":"review-work","mode":"changes","extra":1}', 'invalid_json'),
])
def test_choice_parser_rejects_invalid_wrong_and_excluded_choices(value, error):
    case = evaluator.ChoiceCase('test', 'review changes', 'review-work', 'changes')
    assert evaluator.judge(value, case, {'review-work', 'capture'})['error'] == error


def test_modes_compare_required_tokens_without_ignoring_them():
    case = evaluator.ChoiceCase('test', 'review design', 'ironclad', '--lens')
    assert evaluator.judge('{"skill":"ironclad","mode":"--lens mission"}', case, {'ironclad'})['passed']
    assert not evaluator.judge('{"skill":"ironclad","mode":null}', case, {'ironclad'})['passed']


def test_budget_is_checked_before_running_another_attempt():
    calls = []
    def runner(case):
        calls.append(case.id)
        return json.dumps({'skill': case.expect, 'mode': case.mode})
    cases = [evaluator.ChoiceCase(str(i), 'review changes', 'review-work', 'changes') for i in range(4)]
    report = evaluator.evaluate(cases, {'review-work'}, runner, max_attempts=2)
    assert calls == ['0', '1']
    assert report['stop_reason'] == 'attempt_budget'
    assert report['complete'] is False


@pytest.mark.parametrize(('exception', 'error'), [
    (subprocess.TimeoutExpired('codex', 1), 'timeout'),
    (evaluator.SetupError('auth'), 'auth'),
    (evaluator.SetupError('setup'), 'setup'),
])
def test_errors_are_preserved_and_three_setup_errors_stop(exception, error):
    def runner(case):
        raise exception
    cases = [evaluator.ChoiceCase(str(i), 'review', 'review-work') for i in range(4)]
    report = evaluator.evaluate(cases, {'review-work'}, runner, max_attempts=4)
    assert report['results'][0]['error'] == error
    assert report['attempts'] == (4 if error == 'timeout' else 3)
    assert report['stop_reason'] == (None if error == 'timeout' else 'setup_errors')
    assert all('utterance' not in row for row in report['results'])


def test_catalog_prompt_contains_no_answer_or_hidden_action():
    case = evaluator.ChoiceCase('test', 'review changes', 'review-work', 'changes')
    prompt = evaluator.prompt(case, [{'name': 'review-work', 'description': 'Review changes.'}])
    assert case.utterance in prompt
    assert 'expected' not in prompt.lower()
    assert 'do not execute' in prompt.lower()


def test_negative_control_rejects_overfire():
    case = evaluator.ChoiceCase('control', '17 times 23', None)
    assert evaluator.judge('{"skill":null,"mode":null}', case, {'review-work'})['passed']
    assert evaluator.judge('{"skill":"review-work","mode":null}', case, {'review-work'})['error'] == 'wrong_skill'


def test_live_runner_accepts_an_already_isolated_launcher_home(tmp_path, monkeypatch):
    from types import SimpleNamespace
    paths = {name: tmp_path / name for name in ('home', 'codex', 'work', 'tmp')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    monkeypatch.setenv('HOME', str(paths['home']))
    monkeypatch.setenv('CODEX_HOME', str(paths['codex']))
    args = SimpleNamespace(home=paths['home'], codex_home=paths['codex'], workdir=paths['work'], tmpdir=paths['tmp'])
    owner = evaluator.maintainer_paths('codex-live-test', standalone=True)
    runner, models = evaluator.live_runner(args, [], owner=owner)
    assert callable(runner) and models == set()
    assert owner.directory.is_relative_to(Path(os.environ['CLAUDNA_STATE_DIR']))
    assert owner.directory not in paths.values()


def test_live_runner_refuses_paths_outside_the_private_common_root(tmp_path):
    from types import SimpleNamespace
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    for name in ('codex', 'work', 'tmp'):
        (private / name).mkdir(mode=0o700)
    args = SimpleNamespace(home=tmp_path, codex_home=private / 'codex',
                           workdir=private / 'work', tmpdir=private / 'tmp')
    with pytest.raises(ValueError):
        owner = evaluator.maintainer_paths('codex-live-refusal', standalone=True)
        evaluator.live_runner(args, [], owner=owner)


def test_catalog_retains_only_actual_installed_invocation_hints():
    rows = {row['name']: row for row in evaluator.catalog(evaluator.ROOT)}
    assert rows['review-work']['argument_hint'].startswith('[changes|pr|multi-pr]')
    assert '--lens' in rows['ironclad']['argument_hint']
    assert rows['verify-completion']['argument_hint'] is None


def test_choice_prompt_does_not_change_when_the_oracle_changes():
    descriptions = [{'name': 'review-work', 'description': 'Use when reviewing changes.',
                     'argument_hint': '[changes|pr|multi-pr]'}]
    original = evaluator.ChoiceCase('one', 'Check this change', 'review-work', 'changes')
    changed = evaluator.ChoiceCase('two', 'Check this change', 'capture', 'session')
    assert evaluator.prompt(original, descriptions) == evaluator.prompt(changed, descriptions)
    assert '[changes|pr|multi-pr]' in evaluator.prompt(original, descriptions)


def test_live_runner_retains_exact_private_schema_response(tmp_path, monkeypatch):
    from types import SimpleNamespace
    paths = {name: tmp_path / name for name in ('home', 'codex', 'work', 'tmp')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    args = SimpleNamespace(home=paths['home'], codex_home=paths['codex'], workdir=paths['work'],
                           tmpdir=paths['tmp'], codex_bin='codex', model=None, timeout=2)
    raw = '{"skill":"review-work","mode":"unexpected-mode"}'
    scratch_paths = []
    def fake_run(argv, **kwargs):
        output = Path(argv[argv.index('--output-last-message') + 1])
        scratch_paths.append(output)
        output.write_text(raw)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(evaluator.subprocess, 'run', fake_run)
    owner = evaluator.maintainer_paths('codex-live-private', standalone=True)
    runner, _ = evaluator.live_runner(args, [], owner=owner)
    assert runner(evaluator.ChoiceCase('test', 'Check this change', 'review-work', 'changes')) == raw
    receipt = next(owner.artifacts.glob('private-selection-receipts/run-*/attempt-01/schema-response.txt'))
    assert receipt.read_text() == raw
    assert receipt.stat().st_mode & 0o077 == 0
    assert receipt.is_relative_to(owner.artifacts)
    assert not (paths['tmp'] / 'private-selection-receipts').exists()
    assert scratch_paths[0].is_relative_to(owner.scratch)
    assert not scratch_paths[0].exists()
    assert list(paths['tmp'].iterdir()) == []


def test_live_runner_requires_explicit_standalone_without_native_owner(tmp_path):
    from types import SimpleNamespace
    paths = {name: tmp_path / name for name in ('home', 'codex', 'work', 'tmp')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    args = SimpleNamespace(home=paths['home'], codex_home=paths['codex'], workdir=paths['work'],
                           tmpdir=paths['tmp'], codex_bin='codex', model=None, timeout=2)
    with pytest.raises(ValueError, match='native identity required'):
        evaluator.live_runner(args, [])


def test_explicit_report_is_exported_and_receipted_without_live_allocation(tmp_path):
    report = tmp_path / 'selected report.json'
    assert evaluator.main(['--report', str(report), '--standalone']) == 0
    assert report.stat().st_mode & 0o777 == 0o600
    root = Path(os.environ['CLAUDNA_STATE_DIR'])
    [receipt_path] = list(root.glob('operations/*/artifacts/routing-eval-codex-*.json'))
    receipt = json.loads(receipt_path.read_text())
    assert receipt['owner']['kind'] == 'operation'
    assert receipt['export_path'] == str(report.resolve())
    assert receipt['report_sha256'] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert receipt['source_script_sha256'] == hashlib.sha256(Path(evaluator.__file__).read_bytes()).hexdigest()


def test_floor_without_live_or_report_is_read_only(tmp_path, capsys):
    assert evaluator.main([]) == 0
    capsys.readouterr()
    assert not Path(os.environ['CLAUDNA_STATE_DIR']).exists()


def test_existing_or_dangling_report_path_is_refused_before_floor_or_provider(tmp_path, monkeypatch, capsys):
    existing = tmp_path / 'existing report.json'
    existing.write_text('preserve')
    existing.chmod(0o640)
    monkeypatch.setattr(evaluator, 'floor', lambda *_a, **_k: pytest.fail('floor ran before export refusal'))
    assert evaluator.main(['--report', str(existing), '--live']) == 2
    assert 'already exists' in capsys.readouterr().err
    assert existing.read_text() == 'preserve' and existing.stat().st_mode & 0o777 == 0o640

    dangling = tmp_path / 'dangling report.json'
    dangling.symlink_to(tmp_path / 'missing target')
    assert evaluator.main(['--report', str(dangling)]) == 2
    assert dangling.is_symlink() and not (tmp_path / 'missing target').exists()


def test_live_without_report_keeps_raw_response_private_and_records_summary(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    profile = tmp_path / 'profiles'
    profile.mkdir(mode=0o700)
    paths = {name: profile / name for name in ('home', 'codex', 'work', 'tmp')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    monkeypatch.setattr(evaluator, 'floor', lambda *_a, **_k: {
        'method': evaluator.METHOD, 'errors': [], 'native_automatic_routing': 'not measured'})
    monkeypatch.setattr(evaluator, 'catalog', lambda _root: [{'name': 'review-work', 'description': 'Review.'}])
    case = evaluator.ChoiceCase('case-1', 'review this change', 'review-work', 'changes')
    monkeypatch.setattr(evaluator, 'cases', lambda: [case])
    raw = '{"skill":"review-work","mode":"changes"}'
    child_envs = []

    def fake_run(argv, **kwargs):
        if argv[-1] == '--version':
            return SimpleNamespace(returncode=0, stdout='Codex fixture', stderr='')
        child_envs.append(kwargs['env'])
        Path(argv[argv.index('--output-last-message') + 1]).write_text(raw)
        return SimpleNamespace(returncode=0, stdout='{"model":"fixture"}\n', stderr='')

    monkeypatch.setattr(evaluator.subprocess, 'run', fake_run)
    args = ['--live', '--codex-bin', 'codex', '--home', str(paths['home']),
            '--codex-home', str(paths['codex']), '--workdir', str(paths['work']),
            '--tmpdir', str(paths['tmp']), '--standalone', '--max-attempts', '1']
    assert evaluator.main(args) == 0
    printed = capsys.readouterr().out
    state = Path(os.environ['CLAUDNA_STATE_DIR'])
    [receipt_path] = list(state.glob('operations/*/artifacts/routing-eval-codex-*.json'))
    receipt = json.loads(receipt_path.read_text())
    assert receipt['owner']['kind'] == 'operation' and receipt['export_path'] is None
    assert receipt['report_sha256'] == hashlib.sha256(printed.encode()).hexdigest()
    [raw_path] = list(receipt_path.parent.glob('private-selection-receipts/run-*/attempt-01/schema-response.txt'))
    assert raw_path.read_text() == raw and raw_path.stat().st_mode & 0o777 == 0o600
    assert child_envs[0]['CLAUDNA_STATE_DIR'] == str(state.resolve())
    assert child_envs[0]['HOME'] == str(paths['home'].resolve())
    assert child_envs[0]['TMPDIR'] == str(paths['tmp'].resolve())
    assert list(paths['tmp'].iterdir()) == []


def test_prompt_and_schema_share_the_invocation_suffix_contract():
    rule = evaluator.mode_instruction()
    for requirement in ('invocation suffix', 'verbs', 'selector flags', 'argument_hint',
                        'placeholders', 'do not invent'):
        assert requirement in rule
    schema = evaluator.choice_schema()
    case = evaluator.ChoiceCase('test', 'Review this change', 'review-work', 'changes')
    assert schema['properties']['mode']['description'] == rule
    assert rule in evaluator.prompt(case, [])
    assert 'review-work' not in rule and '--lens' not in rule and 'first-principles' not in rule
