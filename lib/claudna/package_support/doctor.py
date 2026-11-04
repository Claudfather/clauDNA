"""Local package and prerequisite observations; no subprocesses or state writes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Mapping

from .catalog import CLI, HOSTS, InvalidPackage, load

ROOT = Path(__file__).resolve().parents[3]
LIMITS = [
    "Source hashes establish local consistency, not publisher authenticity.",
    "Declared packaging does not establish native installation, discovery, trust or execution.",
    "PATH tools are never executed; a found versioned tool has an unverified version.",
    "Missing baseline tools limit their consumers, not every workflow.",
]


def row(check: str, status: str, summary: str) -> dict:
    return {"id": check, "status": status, "summary": summary}


def _dependency(entry: dict, scope: str, env: Mapping[str, str]) -> dict:
    key = "cli" if "cli" in entry else "env"
    dependency = entry[key]
    if key == "env":
        present = bool(env.get(dependency))
        return row(f"{scope}.env.{dependency}", "pass" if present else "warn",
                   "Environment variable is present; value and authentication unverified."
                   if present else "Required environment variable is absent or empty.")
    match = CLI.fullmatch(dependency)
    name, minimum = match.groups()
    present = shutil.which(name, path=env.get("PATH", "")) is not None
    status = "unknown" if present and minimum else "pass" if present else "warn"
    detail = (f"Present on PATH; minimum {minimum} unverified (not executed)." if minimum
              else "Present on PATH; not executed or authenticated.") if present else "Missing from PATH."
    if scope == "baseline":
        detail += " Limits only workflows that use this tool."
        if name == "jq":
            detail += " The Claude permission hook silently does nothing without jq."
    return row(f"{scope}.cli.{name}", status, detail)


def diagnose(*, root: Path = ROOT, host: str, skill: str | None = None,
             store_root: Path | None = None, env: Mapping[str, str] | None = None) -> dict:
    """Stable JSON contract; unknowns do not themselves produce a nonzero exit."""
    env = os.environ if env is None else env
    result = {"schema": "claudna.package-doctor/1", "host": host if host in HOSTS else None,
              "skill": None, "package_version": None, "status": "observed", "exit_code": 0,
              "checks": [], "pipeline_health": None, "limits": LIMITS}
    checks = result["checks"]
    if host not in HOSTS:
        checks.append(row("request.host", "fail", "Unknown host; choose claude-code, cursor or codex."))
        result.update(status="invalid", exit_code=2)
        return result
    try:
        catalog = load(root.resolve())
    except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
        code = str(exc) if isinstance(exc, InvalidPackage) else "unreadable_metadata"
        checks.append(row("package.integrity", "fail", f"Package diagnosis unavailable: {code}."))
        result.update(status="invalid", exit_code=2)
        return result
    result["package_version"] = catalog["package_version"]
    settings = catalog["hosts"][host]
    checks.append(row("package.integrity", "pass", "Projection schema, source hashes and bundled paths agree."))
    checks.append(row("package.selection", "pass",
                      f"Manifest declares {settings['skill_count']} skills and "
                      f"{settings['hooks']['handler_count']} hook handlers for this host."))
    if skill is not None and skill not in settings["skills"]:
        checks.append(row("request.skill", "fail", "Skill is unknown or excluded from this host's manifest."))
        result.update(status="invalid", exit_code=2)
        return result
    result["skill"] = skill
    checks.append(row("runtime.python", "pass" if sys.version_info >= (3, 9) else "fail",
                      f"Doctor interpreter {'.'.join(map(str, sys.version_info[:3]))}; Python 3.9+ required."))
    platform = {"darwin": "macOS", "linux": "Linux"}.get(sys.platform)
    platforms = settings["runtime_platforms"]
    checks.append(row("runtime.platform", "pass" if not platforms or platform in platforms else "fail",
                      "No hook runtime is declared for this host." if not platforms else
                      "Host hook runtime supports this platform." if platform in platforms else
                      "Host hook runtime does not support this platform."))
    for entry in settings["runtime_prerequisites"]:
        checks.append(_dependency(entry, "baseline", env))
    if skill:
        for entry in catalog["skills"][skill]["requires"]:
            checks.append(_dependency(entry, "skill", env))
        if catalog["skills"][skill]["requires_context"]:
            checks.append(row("skill.context", "unknown", "Requires a source checkout; execution context unverified."))
    for evidence in ("installed", "discovered", "trusted", "executed"):
        checks.append(row(f"native.{evidence}", "unknown", "Not observed by this local package diagnostic."))
    if store_root is None:
        checks.append(row("pipeline.health", "unknown",
                          "Not requested; use an explicit --store-root to read retained evidence."))
    else:
        try:
            from claudna.session_store.health import report
            from claudna.session_store.store import SessionStore

            health = report(SessionStore(store_root), env=env)
            result["pipeline_health"] = health
            checks.append(row("pipeline.health", "warn" if health["status"] == "attention" else "unknown",
                              f"Retained pipeline evidence: {health['status']}; not a whole-system health verdict."))
        except (OSError, ValueError, TypeError, RuntimeError, ImportError, KeyError, AttributeError):
            checks.append(row("pipeline.health", "fail",
                              "Explicit store evidence is unavailable; no repair attempted."))
    if any(check["status"] in {"fail", "warn"} for check in checks):
        result.update(status="attention", exit_code=1)
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes rejected values, which could contain secrets.
        raise ValueError("invalid arguments")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _Parser(prog="python3 -B <loaded-root>/lib/claudna/package_support", description=__doc__,
                     epilog="Keep -B: Python can write an entrypoint cache before the doctor starts.")
    parser.add_argument("command", choices=["doctor"])
    parser.add_argument("--host", required=True, help="claude-code, cursor or codex")
    parser.add_argument("--skill", help="Selected workflow whose prerequisites to inspect")
    parser.add_argument("--root", type=Path, default=ROOT, help="Explicit package root (default: loaded package)")
    parser.add_argument("--store-root", type=Path, help="Explicit existing session-store evidence; never initialized")
    parser.add_argument("--json", action="store_true", help="Emit claudna.package-doctor/1")
    try:
        args = parser.parse_args(argv)
    except ValueError:
        result = {"schema": "claudna.package-doctor/1", "host": None, "skill": None,
                  "package_version": None, "status": "invalid", "exit_code": 2,
                  "checks": [row("request.arguments", "fail", "Invalid arguments; use --help for usage.")],
                  "pipeline_health": None, "limits": LIMITS}
        as_json = "--json" in argv
    else:
        result = diagnose(root=args.root, host=args.host, skill=args.skill, store_root=args.store_root)
        as_json = args.json
    if as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        version = result["package_version"] or "unknown"
        print(f"Package doctor: {result['status']} (exit {result['exit_code']}); package {version}")
        for check in result["checks"]:
            print(f"{check['status'].upper():7} {check['id']}: {check['summary']}")
        for limit in result["limits"]:
            print(f"Limit: {limit}")
    return result["exit_code"]
