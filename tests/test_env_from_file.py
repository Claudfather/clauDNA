"""scripts/env_from_file.py hands dotenv values to one command without running the file or showing them."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "env_from_file.py"
PROBE = "import os, sys; print(os.environ.get('TARGET')); print(sys.argv[1:])"
# Prints every PG* variable the command received, and its argv.
PG_PROBE = (
    "import json, os, sys; "
    "print(json.dumps({'env': {k: v for k, v in os.environ.items() if k.startswith('PG')}, 'argv': sys.argv[1:]}))"
)
# A made-up URL: every part is percent-encoded where it can be, so decoding is tested too.
URL = (
    "postgresql://fake%40user:s%3Acret-fake-pw@db.example.test:6543/app%20db"
    "?sslmode=require&channel_binding=require&options=endpoint%3Dep-fake"
)
EXPANDED = {
    "PGHOST": "db.example.test",
    "PGPORT": "6543",
    "PGUSER": "fake@user",
    "PGPASSWORD": "s:cret-fake-pw",
    "PGDATABASE": "app db",
    "PGSSLMODE": "require",
    "PGCHANNELBINDING": "require",
    "PGOPTIONS": "endpoint=ep-fake",
}


def _run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, env=env)


def _probe(run: subprocess.CompletedProcess) -> dict:
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


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
    run = _run(".env", "DATABASE_URL=TARGET", "--", sys.executable, "-c", PROBE, "plain-arg", cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    env_line, argv_line = run.stdout.splitlines()
    assert env_line == "postgres://u:secret@h/db"
    assert "secret" not in argv_line


def test_the_file_is_read_as_text_never_run(tmp_path):
    (tmp_path / ".env").write_text('DATABASE_URL="$(touch ran-by-shell)`touch ran-by-backtick`"\n')
    run = _run(".env", "DATABASE_URL=TARGET", "--", sys.executable, "-c", PROBE, cwd=tmp_path)
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


# A Postgres URL becomes libpq's own variables. libpq does not read a URL from
# PGDATABASE (it takes the whole string as a database name).


def test_a_postgres_url_becomes_libpq_variables_and_never_an_argument(tmp_path):
    (tmp_path / ".env").write_text(f"DATABASE_URL='{URL}'\n")
    run = _run(".env", "DATABASE_URL=@libpq", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path)
    seen = _probe(run)
    assert seen["env"] == EXPANDED
    assert seen["argv"] == []
    assert "cret-fake-pw" not in run.stderr


def test_the_url_alone_decides_the_target(tmp_path):
    # A service or host address already in the environment would outrank or
    # redirect the URL's host, so every inherited PG* variable is dropped.
    (tmp_path / ".env").write_text(f"DATABASE_URL={URL}\n")
    env = {**os.environ, "PGSERVICE": "elsewhere", "PGHOSTADDR": "192.0.2.1", "PGPASSWORD": "other-fake"}
    run = _run(".env", "DATABASE_URL=@libpq", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path, env=env)
    assert _probe(run)["env"] == EXPANDED


def test_a_socket_directory_host_is_decoded_with_its_case_kept(tmp_path):
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://%2Ftmp%2FSockDir/app\n")
    run = _run(".env", "DATABASE_URL=@libpq", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path)
    assert _probe(run)["env"] == {"PGHOST": "/tmp/SockDir", "PGDATABASE": "app"}


def test_a_value_libpq_cannot_take_as_a_url_is_refused_without_showing_it(tmp_path):
    for value in (
        "mysql://u:topsecret-fake@h/db",
        "host=h password=topsecret-fake",
        "postgresql://u:topsecret-fake@h1:5432,h2:5432/db",
    ):
        (tmp_path / ".env").write_text(f"DATABASE_URL={value}\n")
        run = _run(".env", "DATABASE_URL=@libpq", "--", "touch", "ran", cwd=tmp_path)
        assert run.returncode == 2 and "DATABASE_URL" in run.stderr, value
        assert "topsecret" not in run.stdout + run.stderr
        assert not (tmp_path / "ran").exists()


def test_an_unknown_url_parameter_is_named_but_its_value_is_not_shown(tmp_path):
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://h/db?mystery=hidden-fake\n")
    run = _run(".env", "DATABASE_URL=@libpq", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path)
    assert _probe(run)["env"] == {"PGHOST": "h", "PGDATABASE": "db"}
    assert "mystery" in run.stderr and "hidden-fake" not in run.stderr


def test_url_file_takes_the_first_line_of_the_file(tmp_path):
    # How a Neon branch URL travels: the CLI writes it to a file with `>`,
    # so it never reaches the session.
    (tmp_path / "branch.url").write_text(URL + "\nnot this line\n")
    run = _run("--url-file", "branch.url", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path)
    assert _probe(run)["env"] == EXPANDED


def test_url_env_takes_the_url_from_a_variable_the_session_already_has(tmp_path):
    env = {**os.environ, "DATABASE_URL": URL}
    run = _run("--url-env", "DATABASE_URL", "--", sys.executable, "-c", PG_PROBE, cwd=tmp_path, env=env)
    seen = _probe(run)
    assert seen["env"] == EXPANDED and seen["argv"] == []


def test_url_env_runs_nothing_when_the_variable_is_empty_or_missing(tmp_path):
    for env in ({**os.environ, "DATABASE_URL": ""}, {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}):
        run = _run("--url-env", "DATABASE_URL", "--", "touch", "ran", cwd=tmp_path, env=env)
        assert run.returncode == 2 and "DATABASE_URL" in run.stderr
        assert not (tmp_path / "ran").exists()
