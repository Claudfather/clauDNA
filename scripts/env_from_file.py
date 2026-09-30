#!/usr/bin/env python3
"""Hand values from a dotenv file to one command, without running the file or showing the values.

    env_from_file.py <env-file> --has KEY [KEY ...]
        Print the first KEY that holds a non-empty value, or nothing and exit 1.
        Only the NAME is printed, never the value.

    env_from_file.py <env-file> KEY[=NAME] [KEY[=NAME] ...] -- COMMAND [ARGS ...]
        Run COMMAND with each KEY's value in its environment, renamed to NAME when
        given. NAME `@libpq` means the value is a Postgres URL (see below).

    env_from_file.py --url-file <file> -- COMMAND [ARGS ...]
        The first line of <file> is a Postgres URL: a Neon branch's connection string
        written there with `>`, so it never reaches the session.

    env_from_file.py --url-env <NAME> -- COMMAND [ARGS ...]
        The environment variable <NAME> holds a Postgres URL.

A Postgres URL is expanded into libpq's own variables (PGHOST, PGPORT, PGUSER,
PGPASSWORD, PGDATABASE, and PGSSLMODE, PGOPTIONS and the like from its query
string), after every PG* variable already in the environment is left out, so the
URL alone decides where the command connects. libpq does not read a URL from
PGDATABASE (it takes the whole string as a database name).

A value reaches the command's environment only: never its argv, never this script's
output. A missing or empty value exits 2 without running COMMAND. The dotenv file is
read as text, line by line (`KEY=value`, `export KEY=value`, quoted values, `#`
comments); nothing in it is expanded or executed, so `$VAR` and `$(...)` stay literal.
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

USAGE = (
    "usage: env_from_file.py <env-file> --has KEY [KEY ...]\n"
    "       env_from_file.py <env-file> KEY[=NAME|=@libpq] [...] -- COMMAND [ARGS ...]\n"
    "       env_from_file.py --url-file <file> -- COMMAND [ARGS ...]\n"
    "       env_from_file.py --url-env <NAME> -- COMMAND [ARGS ...]"
)
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_LIBPQ_VARIABLE = re.compile(r"PG[A-Z]+")
# Connection parameters a URL's query string may carry, and libpq's variable for each.
_QUERY_TO_ENV = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "passfile": "PGPASSFILE",
    "sslmode": "PGSSLMODE",
    "sslnegotiation": "PGSSLNEGOTIATION",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "channel_binding": "PGCHANNELBINDING",
    "gssencmode": "PGGSSENCMODE",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "options": "PGOPTIONS",
    "application_name": "PGAPPNAME",
    "connect_timeout": "PGCONNECT_TIMEOUT",
}


class Refused(ValueError):
    """The request cannot be run as written. The message never holds a value."""


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


def libpq_env(url: str, source: str) -> dict[str, str]:
    """libpq's variables for a Postgres URL. Errors name the source, never the value."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as err:
        raise Refused(f"{source} is not a URL libpq can use") from err
    if parts.scheme not in ("postgres", "postgresql"):
        raise Refused(f"{source} is not a postgres:// or postgresql:// URL")
    userinfo, _, hostport = parts.netloc.rpartition("@")
    if hostport.startswith("["):
        host, _, after = hostport[1:].partition("]")
        port = after[1:] if after.startswith(":") else after
    else:
        host, _, port = hostport.partition(":")
    if port and not re.fullmatch(r"[0-9]+", port):
        raise Refused(f"{source} names more than one host or a port that is not a number")
    user, has_password, password = userinfo.partition(":")
    env = {}
    for name, value in (
        ("PGHOST", unquote(host)),  # unquoted, not lowercased: it may be a socket directory
        ("PGPORT", port),
        ("PGUSER", unquote(user)),
        ("PGPASSWORD", unquote(password) if has_password else ""),
        ("PGDATABASE", unquote(parts.path.lstrip("/"))),
    ):
        if value:
            env[name] = value
    for key, value in parse_qsl(parts.query):
        if key in _QUERY_TO_ENV:
            env[_QUERY_TO_ENV[key]] = value
        else:
            print(f"env_from_file: {source}: URL parameter {key!r} has no libpq variable; ignored", file=sys.stderr)
    return env


def _run(additions: dict[str, str], command: list[str], *, url: bool) -> int:
    env = {k: v for k, v in os.environ.items() if not (url and _LIBPQ_VARIABLE.fullmatch(k))}
    env.update(additions)
    try:
        os.execvpe(command[0], command, env)
    except OSError as err:
        print(f"env_from_file: cannot run {command[0]}: {err.strerror}", file=sys.stderr)
        return 127
    return 0  # not reached: exec replaced this process


def _command(rest: list[str]) -> list[str]:
    if rest[:1] != ["--"] or len(rest) < 2:
        raise Refused("give the command after --")
    return rest[1:]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        if argv[0] in ("--url-file", "--url-env"):
            source, command = argv[1], _command(argv[2:])
            if argv[0] == "--url-file":
                with open(source, encoding="utf-8") as fh:
                    url = fh.readline()
            else:
                url = os.environ.get(source, "")
            if not url.strip():
                raise Refused(f"{source} holds no URL; the command was not run")
            return _run(libpq_env(url, source), command, url=True)

        path, rest = argv[0], argv[1:]
        values = parse(path)
        if rest[0] == "--has":
            for key in rest[1:]:
                if values.get(key):
                    print(key)
                    return 0
            return 1

        if "--" not in rest:
            raise Refused("give the command after --")
        split = rest.index("--")
        pairs, command = rest[:split], _command(rest[split:])
        if not pairs:
            raise Refused("name at least one KEY")
        additions: dict[str, str] = {}
        url = False
        for pair in pairs:
            key, _, name = pair.partition("=")
            if not values.get(key):
                raise Refused(f"{key} is not set in {path}; the command was not run")
            if name == "@libpq":
                additions.update(libpq_env(values[key], key))
                url = True
            else:
                additions[name or key] = values[key]
        return _run(additions, command, url=url)
    except Refused as why:
        print(f"env_from_file: {why}", file=sys.stderr)
        return 2
    except OSError as err:
        print(f"env_from_file: cannot read {err.filename}: {err.strerror}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
