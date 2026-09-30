"""scripts/env_from_file.py hands dotenv values to one command without running the file or showing them."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "env_from_file.py"
PROBE = "import os, sys; print(os.environ.get('PGDATABASE')); print(sys.argv[1:])"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)


def test_has_names_the_first_key_that_holds_a_value_and_never_the_value(tmp_path):
    (tmp_path / ".env").write_text("NEON_PROD_URL=\nDATABASE_URL=postgres://u:secret@h/db\n")
    run = _run(".env", "--has", "NEON_PROD_URL", "DATABASE_URL", cwd=tmp_path)
    assert (run.returncode, run.stdout) == (0, "DATABASE_URL\n")
    assert "secret" not in run.stdout + run.stderr


def test_has_exits_1_when_no_key_holds_a_value(tmp_path):
    (tmp_path / ".env").write_text("A=\n")
    assert _run(".env", "--has", "A", "B", cwd=tmp_path).returncode == 1


def test_a_value_reaches_the_command_environment_renamed_and_not_its_argv(tmp_path):
    (tmp_path / ".env").write_text("export DATABASE_URL='postgres://u:secret@h/db'\n")
    run = _run(".env", "DATABASE_URL=PGDATABASE", "--", sys.executable, "-c", PROBE, "plain-arg", cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    env_line, argv_line = run.stdout.splitlines()
    assert env_line == "postgres://u:secret@h/db"
    assert "secret" not in argv_line


def test_the_file_is_read_as_text_never_run(tmp_path):
    (tmp_path / ".env").write_text('DATABASE_URL="$(touch ran-by-shell)`touch ran-by-backtick`"\n')
    run = _run(".env", "DATABASE_URL=PGDATABASE", "--", sys.executable, "-c", PROBE, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines()[0] == "$(touch ran-by-shell)`touch ran-by-backtick`"
    assert not (tmp_path / "ran-by-shell").exists() and not (tmp_path / "ran-by-backtick").exists()


def test_a_missing_key_runs_nothing(tmp_path):
    (tmp_path / ".env").write_text("OTHER=x\n")
    run = _run(".env", "DATABASE_URL", "--", "touch", "ran", cwd=tmp_path)
    assert run.returncode == 2 and "not set" in run.stderr
    assert not (tmp_path / "ran").exists()


def test_comments_quotes_and_export_parse(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("env_from_file", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / ".env").write_text(
        "# a comment\n\nexport A=one\nB = \"two words\"\nC='three' \nD=four # trailing note\nnot a line\n"
    )
    assert mod.parse(str(tmp_path / ".env")) == {"A": "one", "B": "two words", "C": "three", "D": "four"}
