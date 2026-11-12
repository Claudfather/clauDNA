#!/usr/bin/env python3
"""Deterministic Codex catalog floor; optional bounded model catalog choices.

This does not measure native automatic skill loading. Live mode sends only a
public utterance and installed names/descriptions/invocation hints, without executing the chosen skill.
It never invokes Claude. Private homes/auth are prepared by the operator, not
copied or modified by this script. Reports omit raw prompt, tool and auth content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

import yaml

sys.dont_write_bytecode = True

from check_codex_scope import run_check, selected_names  # noqa: E402
from routing_eval import _fresh_output, _open_exclusive_output, load_cases  # noqa: E402
from release_toolchain import MaintainerPaths, maintainer_paths  # noqa: E402
from skill_checks import parse_frontmatter  # noqa: E402
from claudna.session_store.fsio import atomic_write_json, ensure_dir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COVERAGE = ROOT / 'tests/fixtures/routing-codex.yaml'
METHOD = 'catalog_selection'


@dataclass(frozen=True)
class ChoiceCase:
    id: str
    utterance: str
    expect: str | None
    mode: str | None = None


class SetupError(Exception):
    """A classified setup error; raw stderr must stay outside public reports."""


def catalog(root: Path) -> list[dict]:
    names = selected_names(root)
    rows = []
    for name in sorted(names):
        data, _ = parse_frontmatter(root / 'skills' / name / 'SKILL.md')
        rows.append({'name': name, 'description': data['description'],
                     'argument_hint': data.get('argument-hint')})
    return rows


def cases(*, all_rows: bool = False) -> list[ChoiceCase]:
    source = load_cases(all_rows=all_rows)
    result = [ChoiceCase(f'source-{i:02}', row.utterance, row.expect, row.mode)
              for i, row in enumerate(source)]
    additions = yaml.safe_load(COVERAGE.read_text())
    result.extend(ChoiceCase(row['id'], row['utterance'], row['expect'], row.get('mode'))
                  for row in additions['pairs'])
    return result


def floor(root: Path = ROOT) -> dict:
    errors, _, _ = run_check(root)
    declared = catalog(root) if not errors else []
    names = {row['name'] for row in declared}
    coverage = yaml.safe_load(COVERAGE.read_text())
    positives = {row['expect'] for row in coverage['positives']}
    if names != positives:
        errors.append(f'positive coverage mismatch: missing={sorted(names - positives)}, '
                      f'extra={sorted(positives - names)}')
    if any(not row['description'].strip() for row in declared):
        errors.append('empty catalog description')
    unsupported = sorted({row.expect for row in load_cases(all_rows=True)
                          if row.expect and row.expect not in names})
    if unsupported != ['promotion-intake']:
        errors.append('unexpected source host filtering')
    pairs = coverage['pairs']
    if len(pairs) != 6 or len({row['id'] for row in pairs}) != 6:
        errors.append('expected six unique confusable pairs')
    return {'method': METHOD, 'selected': len(names), 'source_rows': len(load_cases(all_rows=True)) - 2,
            'controls': 2, 'positive_coverage': len(positives), 'live_cases': len(cases()),
            'unsupported': [{'skill': name, 'reason': 'requires repo-clone context'} for name in unsupported],
            'errors': errors, 'native_automatic_routing': 'not measured',
            'catalog_input': 'installed names, descriptions and argument-hint; no fixture answers'}


def mode_instruction() -> str:
    return ('The mode is the routing invocation suffix after the selected skill name. '
            'Preserve literal verbs or selector flags from its actual argument_hint and values supplied '
            'by the utterance. Omit unavailable positional placeholders; do not invent arguments. '
            'Use null when no suffix applies.')


def choice_schema() -> dict:
    return {'type': 'object', 'properties': {'skill': {'type': ['string', 'null']},
            'mode': {'type': ['string', 'null'], 'description': mode_instruction()}},
            'required': ['skill', 'mode'], 'additionalProperties': False}


def prompt(case: ChoiceCase, descriptions: list[dict]) -> str:
    return ('Choose one skill from this installed catalog and its invocation hints, '
            'or null when none fits. ' + mode_instruction()
            + ' Do not execute any skill, read project files or use tools. Return only the schema result.\n'
            + json.dumps({'catalog': descriptions, 'utterance': case.utterance}, ensure_ascii=False))


def judge(raw: str, case: ChoiceCase, selected: set[str]) -> dict:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {'skill', 'mode'}:
            raise ValueError
        skill, mode = value['skill'], value['mode']
        if skill is not None and not isinstance(skill, str):
            raise ValueError
        if mode is not None and not isinstance(mode, str):
            raise ValueError
    except (ValueError, TypeError):
        return {'passed': False, 'skill': None, 'mode': None, 'error': 'invalid_json'}
    if skill is not None and skill not in selected:
        return {'passed': False, 'skill': None, 'mode': None, 'error': 'excluded_skill'}
    if skill != case.expect:
        return {'passed': False, 'skill': skill, 'mode': mode if mode == case.mode else None, 'error': 'wrong_skill'}
    try:
        required = shlex.split(case.mode or '')
        actual = shlex.split(mode or '')
    except ValueError:
        actual = []
        required = ['invalid']
    passed = all(token in actual for token in required)
    # Only known fixture tokens enter a public report; arbitrary model output does not.
    return {'passed': passed, 'skill': skill, 'mode': case.mode if passed else None,
            'error': None if passed else 'wrong_mode'}


def evaluate(rows: list[ChoiceCase], selected: set[str], runner: Callable,
             *, max_attempts: int = 18) -> dict:
    results = []
    consecutive_setup_errors = 0
    stop = None
    for case in rows:
        if len(results) >= max_attempts:
            stop = 'attempt_budget'
            break
        started = time.monotonic()
        try:
            result = judge(runner(case), case, selected)
            consecutive_setup_errors = 0
        except subprocess.TimeoutExpired:
            result = {'passed': False, 'skill': None, 'mode': None, 'error': 'timeout'}
            consecutive_setup_errors = 0
        except SetupError as exc:
            error = 'auth' if str(exc) == 'auth' else 'setup'
            result = {'passed': False, 'skill': None, 'mode': None, 'error': error}
            consecutive_setup_errors += 1
        results.append({'id': case.id, **result, 'seconds': round(time.monotonic() - started, 3)})
        if consecutive_setup_errors >= 3:
            stop = 'setup_errors'
            break
    return {'method': METHOD, 'attempts': len(results), 'complete': len(results) == len(rows),
            'stop_reason': stop, 'results': results, 'native_automatic_routing': 'not measured'}


def live_runner(args, descriptions: list[dict], *, owner: MaintainerPaths | None = None,
                session: str | None = None, host: str | None = None, standalone: bool = False):
    if owner is None:
        owner = maintainer_paths("routing-eval-codex", session=session, host=host, standalone=standalone)
    raw_paths = (args.home, args.codex_home, args.workdir, args.tmpdir)
    home, codex_home, work, temporary = (p.resolve() for p in raw_paths)
    profile_root = temporary.parent
    for raw, path in zip(raw_paths, (home, codex_home, work, temporary)):
        if (raw.is_symlink() or not path.is_dir() or path == profile_root
                or not path.is_relative_to(profile_root) or path.stat().st_mode & 0o077):
            raise ValueError('live evaluation requires private directories within the isolated tmp parent')
    effective_root = owner.directory.parents[1].resolve()
    env = {'CLAUDNA_STATE_DIR': str(effective_root), 'HOME': str(home),
           'CODEX_HOME': str(codex_home), 'TMPDIR': str(args.tmpdir.resolve()),
           'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'CLAUDNA_SESSION_BRIEFING': '0',
           'CLAUDNA_SESSION_SUMMARY': '0', 'CLAUDNA_HARVEST': '0'}
    schema = choice_schema()
    observed_models = set()
    receipt_root = ensure_dir(owner.artifacts / 'private-selection-receipts')
    receipts = receipt_root / f'run-{uuid4().hex}'
    receipts.mkdir(mode=0o700)
    receipts.chmod(0o700)
    sequence = 0

    def run(case):
        nonlocal sequence
        sequence += 1
        receipt = receipts / f'attempt-{sequence:02}'
        receipt.mkdir(mode=0o700)
        receipt.chmod(0o700)

        def retain(name: str, text: str):
            path = receipt / name
            path.write_text(text)
            path.chmod(0o600)
        with tempfile.TemporaryDirectory(prefix='codex-choice-', dir=owner.scratch) as directory:
            scratch = Path(directory)
            schema_path, output = scratch / 'schema.json', scratch / 'result.json'
            schema_path.write_text(json.dumps(schema))
            schema_path.chmod(0o600)
            argv = [args.codex_bin, '--no-daemon', 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
                    '--sandbox', 'read-only', '--skip-git-repo-check', '--json', '--color', 'never',
                    '--disable', 'apps', '--disable', 'recommended_plugins', '--disable', 'chronicle',
                    '--disable', 'memories', '-c', 'analytics.enabled=false',
                    '-c', 'otel.exporter="none"', '-c', 'otel.metrics_exporter="none"',
                    '-c', 'otel.trace_exporter="none"', '-c', 'otel.log_user_prompt=false',
                    '--output-schema', str(schema_path), '--output-last-message', str(output),
                    '-C', str(work)]
            if args.model:
                argv += ['--model', args.model]
            argv += ['-']
            result = subprocess.run(argv, input=prompt(case, descriptions), text=True,
                                    capture_output=True, timeout=args.timeout, env=env, cwd=work)
            retain('stdout.jsonl', result.stdout)
            retain('stderr.txt', result.stderr)
            retain('metadata.json', json.dumps({'id': case.id, 'returncode': result.returncode}))
            if output.is_file():
                retain('schema-response.txt', output.read_text())
            if result.returncode:
                lowered = result.stderr.lower()
                auth_error = any(s in lowered for s in ('unauthorized', 'not logged', '401', 'authentication'))
                raise SetupError('auth' if auth_error else 'setup')
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                    if isinstance(event.get('model'), str):
                        observed_models.add(event['model'])
                except (ValueError, AttributeError):
                    continue
            if not output.is_file():
                raise SetupError('setup')
            return output.read_text()
    return run, observed_models


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root', type=Path, default=ROOT)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--codex-bin', default=shutil.which('codex'))
    parser.add_argument('--home', type=Path)
    parser.add_argument('--codex-home', type=Path)
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--tmpdir', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--max-attempts', type=int, default=18)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--session', help='verified native session ID')
    parser.add_argument('--host', choices=('claude', 'codex', 'cursor'), help='native session provider')
    parser.add_argument('--standalone', action='store_true', help='explicitly allocate a standalone operation')
    args = parser.parse_args(argv)
    if args.report:
        try:
            _fresh_output(args.report)
        except OSError as exc:
            print(f'report export unavailable: {exc}', file=sys.stderr)
            return 2
    report = floor(args.plugin_root)
    if args.live:
        if report['errors'] or not args.codex_bin or not all((args.home, args.codex_home, args.workdir, args.tmpdir)):
            parser.error('live mode requires a clean floor, Codex executable and isolated home/work/tmp paths')
        if not 1 <= args.max_attempts <= 18 or not 1 <= args.timeout <= 120:
            parser.error('live limits: 1..18 attempts and 1..120 seconds per attempt')
    owner = None
    if args.live or args.report:
        try:
            owner = maintainer_paths('routing-eval-codex', session=args.session, host=args.host,
                                     standalone=args.standalone)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f'maintainer storage unavailable: {exc}', file=sys.stderr)
            return 2
    if args.live:
        descriptions = catalog(args.plugin_root)
        runner, models = live_runner(args, descriptions, owner=owner)
        version_env = {'HOME': str(args.home.resolve()), 'CODEX_HOME': str(args.codex_home.resolve()),
                       'TMPDIR': str(args.tmpdir.resolve()), 'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
        version = subprocess.run([args.codex_bin, '--version'], capture_output=True, text=True,
                                 timeout=5, env=version_env)
        report = {**report, **evaluate(cases(), {r['name'] for r in descriptions}, runner,
                                    max_attempts=args.max_attempts),
                  'requested_model': args.model, 'observed_models': sorted(models),
                  'model_observation': 'event metadata only; absent means unavailable',
                  'raw_response_receipts': 'retained privately outside this public report',
                  'version': version.stdout.strip() if version.returncode == 0 else 'unavailable'}
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        try:
            with _open_exclusive_output(args.report) as report_file:
                report_file.write(text)
        except OSError as exc:
            print(f'report export unavailable: {exc}', file=sys.stderr)
            return 2
    if owner is not None:
        receipt = {'schema_version': 1, 'tool': 'routing-eval-codex', 'owner': {
            'kind': owner.kind, 'owner_id': owner.owner_id, 'provider': owner.provider},
            'export_path': str(args.report.resolve()) if args.report else None,
            'report_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'source_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'outcome': {'live': args.live, 'attempts': report.get('attempts', 0),
                        'complete': report.get('complete', True)}}
        atomic_write_json(owner.artifacts / f'routing-eval-codex-{uuid4().hex}.json', receipt, durable=True)
    print(text, end='')
    failed_live = args.live and (not report['complete'] or not all(r['passed'] for r in report['results']))
    return int(bool(report['errors']) or failed_live)


if __name__ == '__main__':
    raise SystemExit(main())
