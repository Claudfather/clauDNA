"""Tests for the agent memory-scope rule: an agent that can run shell must not
use user-scoped (global) memory.

An agent with Bash acts on whatever it reads; production logs and query results
are attacker-influenceable. If such an agent also keeps user-scoped memory, a
followed injection persists across every project the user opens, not just the
session it appeared in. The rule requires memory: project or memory: none for
any agent whose tools include Bash. Reviewer agents (memory: none + Bash) and
data agents already on memory: project are unaffected.

The new function is reached by module attribute so a missing implementation
fails as an assertion error, not a collection error that silences the file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("validate_agents", REPO_ROOT / "scripts" / "validate-agents.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def scope(fm):
    return _mod.check_agent_memory_scope(fm)


class TestFlagged:
    def test_bash_plus_user_memory_rejected(self):
        fm = {"memory": "user", "tools": ["Bash", "Read"], "background": True}
        errs = scope(fm)
        assert errs
        assert "memory" in errs[0]

    def test_bash_plus_user_memory_without_background_still_rejected(self):
        # background makes it worse, but it is not the load-bearing part -- a
        # foreground agent with shell and global memory persists an injection too.
        fm = {"memory": "user", "tools": ["Bash"]}
        assert scope(fm)


class TestAllowed:
    def test_bash_plus_project_memory_ok(self):
        fm = {"memory": "project", "tools": ["Bash", "Read"], "background": True}
        assert scope(fm) == []

    def test_bash_plus_no_memory_ok(self):
        # reviewer shape: shell but memory: none.
        fm = {"memory": "none", "tools": ["Bash", "Read", "Grep", "Glob"]}
        assert scope(fm) == []

    def test_user_memory_without_bash_ok(self):
        # No shell to act on a followed injection; user memory alone is not the risk.
        fm = {"memory": "user", "tools": ["Read", "Grep", "Glob"]}
        assert scope(fm) == []

    def test_no_memory_field_ok(self):
        fm = {"tools": ["Bash", "Read"]}
        assert scope(fm) == []

    def test_no_tools_field_ok(self):
        fm = {"memory": "user"}
        assert scope(fm) == []


class TestWiredIntoValidator:
    def test_validate_agent_rejects_bash_user_memory(self, tmp_path):
        a = tmp_path / "prod-ops.md"
        a.write_text(
            "---\n"
            "name: prod-ops\n"
            'description: "SRE agent that reads production logs and diagnoses incidents."\n'
            "background: true\n"
            "memory: user\n"
            "tools:\n"
            "  - Bash\n"
            "  - Read\n"
            "---\n\n"
            "Body describing the agent in enough detail to clear the "
            "minimum-length contract check: it reads production logs, "
            "correlates deploys, and reports probable causes without "
            "taking mutating actions on the infrastructure itself.\n"
        )
        errors = _mod.validate_agent(a)
        assert any("memory" in e for e in errors)

    def test_validate_agent_accepts_bash_project_memory(self, tmp_path):
        a = tmp_path / "prod-ops.md"
        a.write_text(
            "---\n"
            "name: prod-ops\n"
            'description: "SRE agent that reads production logs and diagnoses incidents."\n'
            "background: true\n"
            "memory: project\n"
            "tools:\n"
            "  - Bash\n"
            "  - Read\n"
            "---\n\n"
            "Body describing the agent in enough detail to clear the "
            "minimum-length contract check: it reads production logs, "
            "correlates deploys, and reports probable causes without "
            "taking mutating actions on the infrastructure itself.\n"
        )
        errors = _mod.validate_agent(a)
        assert errors == []
