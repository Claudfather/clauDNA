"""A virtualenv in the repo root must not be walked by the repo-wide gates.

Two gates walk every text surface in the repo and run a per-line regex over
each file: validate-skills.py's removed-names scan and check_vault_address.py's
conformance gate. A virtualenv is thousands of gate-matching files with long
lines, so one in the repo root turned a ~3s gate into ~98s -- slow enough to
read as a hang, and the misreading held a merge for hours (#330).

Every assertion here drives the REAL production walk over a tree built on disk
in its PRE-fix shape. Nothing hand-builds an already-pruned file list: that
shape passes whether or not the prune works, which is the exact way a gate test
certifies a dead path.

Each negative carries a POSITIVE CONTROL asserting the walk found the living
surface it was supposed to find. Without one, a walk that returned nothing at
all -- broken rather than pruned -- would satisfy every "the venv is absent"
assertion in the file.

Fixture note: the venvs below are created by real ``python3 -m venv``, not
fabricated. The gates key on a ``pyvenv.cfg`` marker, so a hand-made stand-in
would be a fixture asserting the shape this test exists to verify reality
produces. ``--without-pip`` keeps it at ~0.1s.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import skill_checks  # noqa: E402

# The vault-address gate flags a literal assignment of the retired variable, so
# the fixture text below is assembled rather than written out: spelled whole, it
# would trip that same gate against THIS file when it walks tests/.
_RETIRED_VAR = "CLAUDRON_" + "VAULT"


def _load(script_name: str, module_name: str):
    """Import a hyphenated scripts/ module by path (the repo's own test idiom)."""
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / "scripts" / script_name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_venv(root: Path, name: str) -> Path:
    """A real virtualenv at root/name, plus a gate-matching file inside it."""
    venv = root / name
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        check=True,
        capture_output=True,
    )
    assert (venv / "pyvenv.cfg").is_file(), "python -m venv no longer writes the PEP 405 marker"
    planted = venv / "lib" / "planted_by_the_test.py"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text("# vendored content the gates must never read\n")
    return venv


def _living_surface(root: Path) -> Path:
    """A file the gates SHOULD walk -- the positive control for every case."""
    path = root / "skills" / "demo" / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nname: demo\n---\n\nA living surface.\n")
    return path


class TestTheSharedWalk:
    def test_a_virtualenv_in_the_repo_root_is_pruned(self, tmp_path):
        living = _living_surface(tmp_path)
        venv = _make_venv(tmp_path, ".venv")

        walked = skill_checks.walk_gate_files(tmp_path)

        assert living in walked, "positive control: the walk must reach living surfaces"
        assert [p for p in walked if venv in p.parents] == []

    def test_the_marker_decides_not_the_directory_name(self, tmp_path):
        """A venv under an unlisted name is still pruned.

        This is the case a literal name list cannot reach. `.venv313` is what a
        contributor running more than one interpreter actually types, and no
        denylist of names can be written ahead of the names people pick.
        """
        living = _living_surface(tmp_path)
        venv = _make_venv(tmp_path, ".venv313")

        walked = skill_checks.walk_gate_files(tmp_path)

        assert living in walked, "positive control: the walk must reach living surfaces"
        assert ".venv313" not in skill_checks.GATE_PRUNE_DIRS, (
            "this case is only evidence while the name is absent from the literal set"
        )
        assert [p for p in walked if venv in p.parents] == []

    def test_a_directory_named_env_that_is_not_a_virtualenv_is_still_walked(self, tmp_path):
        """The prune must not over-reach.

        `env/` is a plausible name for a TRACKED config directory, which is why
        it is deliberately absent from the literal set. Pruning it by name would
        silently drop real files from a gate whose whole job is to find them --
        a check that stops operating still returns its negative verdict.
        """
        _living_surface(tmp_path)
        config = tmp_path / "env" / "settings.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("key: value\n")

        walked = skill_checks.walk_gate_files(tmp_path)

        assert config in walked

    def test_the_prune_stops_the_descent_rather_than_filtering_after_it(self, tmp_path, monkeypatch):
        """Cost, not just correctness -- and they are different claims.

        Filtering an already-enumerated list yields the same file set while
        still paying to enumerate ~1,500 files. This wraps the real os.walk to
        record what it actually visited, rather than substituting a fake for it.
        """
        _living_surface(tmp_path)
        _make_venv(tmp_path, ".venv")

        visited: list[str] = []
        real_walk = os.walk

        def recording_walk(top, *args, **kwargs):
            for dirpath, dirnames, filenames in real_walk(top, *args, **kwargs):
                visited.append(dirpath)
                yield dirpath, dirnames, filenames

        monkeypatch.setattr(skill_checks.os, "walk", recording_walk)
        skill_checks.walk_gate_files(tmp_path)

        assert visited, "positive control: the recording wrapper must have seen the real walk"
        assert [d for d in visited if ".venv" in Path(d).parts] == []

    def test_is_virtualenv_keys_on_the_pep_405_marker(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert not skill_checks.is_virtualenv(plain)
        assert skill_checks.is_virtualenv(_make_venv(tmp_path, "somename"))


class TestTheProductionGates:
    """End to end through the gate entry points, not the shared helper."""

    def test_removed_names_gate_reports_no_hit_from_inside_a_venv(self, tmp_path, monkeypatch):
        validate_skills = _load("validate-skills.py", "validate_skills")
        venv = _make_venv(tmp_path, ".venv")
        (venv / "lib" / "vendored_doc.md").write_text("see claudna:ghostskill for details\n")

        living = _living_surface(tmp_path)
        monkeypatch.setattr(validate_skills, "REPO_ROOT", tmp_path)

        hits = validate_skills.scan_removed_names(["ghostskill"])
        assert hits == [], f"gate read inside the virtualenv: {hits}"

        # Positive control: the SAME name in a living surface must still flag,
        # or this test would pass against a gate that had stopped matching.
        living.write_text("see claudna:ghostskill for details\n")
        hits = validate_skills.scan_removed_names(["ghostskill"])
        assert [rel for rel, _ in hits] == ["skills/demo/SKILL.md"]

    def test_vault_address_gate_is_unchanged_by_a_venv_in_the_root(self, tmp_path):
        """A delta, not an absolute.

        run_check carries structural expectations about the real repo (it
        reports on its own allowlist), so a synthetic tree errors for reasons
        that have nothing to do with pruning. Asserting the venv changes
        NOTHING is both robust to that noise and the stronger claim: it fails
        if the venv contributes a single error, and it cannot be satisfied by a
        gate that stopped producing errors at all -- the control below pins
        that separately.
        """
        check_vault_address = _load("check_vault_address.py", "check_vault_address")
        living = _living_surface(tmp_path)
        living.write_text(f"Run `export {_RETIRED_VAR}=/srv/vault` first.\n")

        before, _warnings, _notes = check_vault_address.run_check(tmp_path)
        assert any(e.startswith("skills/demo/SKILL.md") for e in before), (
            "positive control: the gate must be flagging the living surface"
        )

        venv = _make_venv(tmp_path, ".venv")
        (venv / "lib" / "vendored_activate.sh").write_text(f"export {_RETIRED_VAR}=/srv/vault\n")

        after, _warnings, _notes = check_vault_address.run_check(tmp_path)
        assert after == before, f"the virtualenv changed the gate's verdict: {set(after) - set(before)}"
