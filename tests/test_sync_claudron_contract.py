"""``scripts/sync_claudron_contract.py``: refresh, check, and move to a release with ``--ref``.

A fake ``claudron`` prints a contract; a throwaway repo stands in for this one, so nothing here
touches the real ``contracts/`` or output-guide.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_schema_drift as csd  # noqa: E402
import sync_claudron_contract as sync  # noqa: E402

CONTRACT = {
    "contract_version": 1,
    "statuses": {"plan": {"canonical": ["draft", "active"], "terminal": ["active"], "legacy": {}, "default": "draft"}},
    "maturity": ["draft", "verified", "canonical"],
}
GUIDE = f"""## 3. Frontmatter

> Rendered from Claudron's `claudron contract --json` @ `v0.9.0`; `maturity: draft | verified | canonical`.

{csd.TABLE_MARKER} -->
| type | canonical | terminal | default | accepted legacy → mapping |
|---|---|---|---|---|
| plan | `draft` | `draft` | `draft` | — |

## 4. Next
"""


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    (root / "contracts").mkdir(parents=True)
    (root / "skills" / "_shared").mkdir(parents=True)
    (root / "contracts" / "claudron.json").write_text("{}\n")
    (root / "contracts" / "claudron.ref").write_text("v0.9.0\n")
    (root / csd.OUTPUT_GUIDE_REL).write_text(GUIDE)
    monkeypatch.setattr(sync, "REPO_ROOT", root)
    monkeypatch.setattr(sync, "SNAPSHOT", root / "contracts" / "claudron.json")
    monkeypatch.setattr(sync, "REF", root / "contracts" / "claudron.ref")
    return root


@pytest.fixture
def claudron(tmp_path) -> str:
    """A `claudron` whose `contract --json` prints CONTRACT in the envelope."""
    path = tmp_path / "claudron"
    envelope = json.dumps({"ok": True, "command": "contract", "data": CONTRACT})
    path.write_text(f"#!/bin/sh\ncat <<'EOF'\n{envelope}\nEOF\n")
    path.chmod(0o755)
    return str(path)


def test_without_ref_it_writes_only_the_contract(repo, claudron):
    assert sync.main(["--claudron", claudron]) == 0
    assert json.loads((repo / "contracts" / "claudron.json").read_text()) == CONTRACT
    assert (repo / "contracts" / "claudron.ref").read_text() == "v0.9.0\n"
    assert (repo / csd.OUTPUT_GUIDE_REL).read_text() == GUIDE


def test_with_ref_it_moves_the_contract_the_pin_and_section_3(repo, claudron):
    assert sync.main(["--claudron", claudron, "--ref", "v0.10.0"]) == 0
    assert (repo / "contracts" / "claudron.ref").read_text() == "v0.10.0\n"
    guide = (repo / csd.OUTPUT_GUIDE_REL).read_text()
    assert "@ `v0.10.0`" in guide
    assert "| plan | `draft`, `active` | `active` | `draft` | — |" in guide
    assert guide.endswith("## 4. Next\n")


@pytest.mark.parametrize("argv", [["--ref", "0.10.0"], ["--ref", "latest"], ["--ref", "v0.10.0", "--check"]])
def test_a_bad_ref_is_refused_before_anything_is_written(repo, claudron, argv):
    with pytest.raises(SystemExit) as exc:
        sync.main(["--claudron", claudron, *argv])
    assert exc.value.code == 2
    assert (repo / "contracts" / "claudron.json").read_text() == "{}\n"


def test_a_guide_it_cannot_render_fails_the_move(repo, claudron):
    """The contract and the pin are written first; a guide without the marked table fails the run (exit 1),
    so the half-moved repo never passes as moved (`make check` then names the table)."""
    (repo / csd.OUTPUT_GUIDE_REL).write_text(GUIDE.replace(csd.TABLE_MARKER, "<!-- not the marker"))
    assert sync.main(["--claudron", claudron, "--ref", "v0.10.0"]) == 1


def test_check_compares_without_writing(repo, claudron):
    assert sync.main(["--claudron", claudron, "--check"]) == 1
    assert (repo / "contracts" / "claudron.json").read_text() == "{}\n"
    sync.main(["--claudron", claudron])
    assert sync.main(["--claudron", claudron, "--check"]) == 0


def test_an_engine_without_the_contract_command_is_an_error(repo, tmp_path):
    old = tmp_path / "old-claudron"
    old.write_text("#!/bin/sh\necho 'usage: claudron ...' >&2\nexit 2\n")
    old.chmod(0o755)
    assert sync.main(["--claudron", str(old)]) == 2
