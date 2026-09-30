#!/usr/bin/env python3
"""Hand values from a dotenv file to one command, without running the file or showing the values.

Two modes:

    env_from_file.py <env-file> --has KEY [KEY ...]
        Print the first KEY that holds a non-empty value, or nothing and exit 1.
        Only the NAME is printed, never the value.

    env_from_file.py <env-file> KEY[=NAME] [KEY[=NAME] ...] -- COMMAND [ARGS ...]
        Run COMMAND with each KEY's value in its environment, renamed to NAME when
        given (for example DATABASE_URL=PGDATABASE for psql). A value reaches the
        command's environment only: never its argv, never this script's output.
        Exits 2 without running COMMAND when a KEY is missing or empty.

The file is read as text, line by line: `KEY=value`, `export KEY=value`, a value
in single or double quotes, `#` comments. Nothing in it is expanded or executed,
so `$VAR` and `$(...)` stay literal. Sourcing a project's file would run it as code.
"""

from __future__ import annotations

import os
import re
import sys

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            m = _LINE.match(raw.rstrip("\n"))
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].rstrip()
            values[key] = value
    return values


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: env_from_file.py <env-file> --has KEY [KEY ...]\n"
            "       env_from_file.py <env-file> KEY[=NAME] [KEY[=NAME] ...] -- COMMAND [ARGS ...]",
            file=sys.stderr,
        )
        return 2
    path, rest = argv[0], argv[1:]
    try:
        values = parse(path)
    except OSError as err:
        print(f"env_from_file: cannot read {path}: {err.strerror}", file=sys.stderr)
        return 2

    if rest[0] == "--has":
        for key in rest[1:]:
            if values.get(key):
                print(key)
                return 0
        return 1

    if "--" not in rest:
        print("env_from_file: give the command after --", file=sys.stderr)
        return 2
    split = rest.index("--")
    pairs, command = rest[:split], rest[split + 1 :]
    if not pairs or not command:
        print("env_from_file: name at least one KEY and a command", file=sys.stderr)
        return 2
    env = dict(os.environ)
    for pair in pairs:
        key, _, name = pair.partition("=")
        if not values.get(key):
            print(f"env_from_file: {key} is not set in {path}; the command was not run", file=sys.stderr)
            return 2
        env[name or key] = values[key]
    try:
        os.execvpe(command[0], command, env)
    except OSError as err:
        print(f"env_from_file: cannot run {command[0]}: {err.strerror}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
