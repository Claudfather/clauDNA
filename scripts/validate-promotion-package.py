#!/usr/bin/env python3
"""Validate a promotion package before submitting to clauDNA.

Pre-flight check that ensures a Claudosseum promotion package is well-formed
and would pass CI. Prevents round-trip failures on promotion PRs.

Usage:
    python scripts/validate-promotion-package.py ./path/to/promotion-package/
    python scripts/validate-promotion-package.py ./path/to/promotion-package/ --json

Exits 0 if all required checks pass, 1 otherwise.

Promotion contract: Claudfather/Claudosseum documentation/planning/promotion-contract.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from skill_checks import validate_skill_md

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# --- Promotion criteria thresholds (from Claudosseum promotion contract) ---

ARENA_THRESHOLDS = {
    "elo_rating": 1400,
    "battles": 5,
    "win_rate": 0.60,
}

JUDGE_THRESHOLDS = {
    "mean_judge_confidence": 65,
    "min_battle_confidence": 40,
}

TELEMETRY_THRESHOLDS = {
    "invocations": 50,
    "success_rate": 0.85,
    "distinct_users": 3,
    "days_in_production": 7,
}

LINEAGE_MIN_CONTENT_CHARS = 100

# --- Manifest schema ---

MANIFEST_REQUIRED_SECTIONS = {
    "schema_version",
    "promotion",
    "skill",
    "criteria_snapshot",
    "claudna",
}

PROMOTION_REQUIRED = {"promoted_at", "promoted_by", "gate_type"}
SKILL_REQUIRED = {"id", "slug", "name", "version", "category", "content_hash"}
CATEGORY_REQUIRED = {"domain", "function", "slug"}
CRITERIA_REQUIRED = {
    "elo_rating",
    "battles",
    "win_rate",
    "wins",
    "losses",
    "draws",
    "mean_judge_confidence",
    "min_battle_confidence",
    "invocations",
    "success_rate",
    "distinct_users",
    "days_in_production",
}
CLAUDNA_REQUIRED = {"target_version", "replaces_skill", "is_update"}


class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def fail(self, msg: str):
        self.passed = False
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_manifest_structure(manifest: dict) -> CheckResult:
    """Validate manifest.json has all required sections and field types."""
    result = CheckResult("manifest_structure")

    for section in MANIFEST_REQUIRED_SECTIONS:
        if section not in manifest:
            result.fail(f"missing required top-level key: {section!r}")

    if "schema_version" in manifest and not isinstance(manifest["schema_version"], str):
        result.fail(
            f"schema_version must be a string, got {type(manifest['schema_version']).__name__}"
        )

    promo = manifest.get("promotion", {})
    if isinstance(promo, dict):
        for field in PROMOTION_REQUIRED:
            if field not in promo:
                result.fail(f"promotion.{field} missing")
        if "promoted_at" in promo:
            try:
                datetime.fromisoformat(promo["promoted_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                result.fail(
                    f"promotion.promoted_at is not a valid ISO datetime: {promo['promoted_at']!r}"
                )

    skill = manifest.get("skill", {})
    if isinstance(skill, dict):
        for field in SKILL_REQUIRED:
            if field not in skill:
                result.fail(f"skill.{field} missing")
        cat = skill.get("category", {})
        if isinstance(cat, dict):
            for field in CATEGORY_REQUIRED:
                if field not in cat:
                    result.fail(f"skill.category.{field} missing")
        elif cat is not None:
            result.fail(f"skill.category must be an object, got {type(cat).__name__}")
        content_hash = skill.get("content_hash", "")
        if (
            isinstance(content_hash, str)
            and content_hash
            and not content_hash.startswith("sha256:")
        ):
            result.fail(
                f"skill.content_hash must start with 'sha256:', got {content_hash!r}"
            )

    criteria = manifest.get("criteria_snapshot", {})
    if isinstance(criteria, dict):
        for field in CRITERIA_REQUIRED:
            if field not in criteria:
                result.fail(f"criteria_snapshot.{field} missing")

    claudna = manifest.get("claudna", {})
    if isinstance(claudna, dict):
        for field in CLAUDNA_REQUIRED:
            if field not in claudna:
                result.fail(f"claudna.{field} missing")

    return result


def validate_content_hash(manifest: dict, skill_md: Path) -> CheckResult:
    """Verify sha256(SKILL.md) matches manifest.skill.content_hash."""
    result = CheckResult("content_hash")

    expected = manifest.get("skill", {}).get("content_hash", "")
    if not expected:
        result.fail("manifest.skill.content_hash is missing or empty")
        return result

    if not expected.startswith("sha256:"):
        result.fail(
            f"content_hash format invalid (expected sha256:..., got {expected!r})"
        )
        return result

    expected_hex = expected[len("sha256:") :]
    actual_hex = hashlib.sha256(skill_md.read_bytes()).hexdigest()

    if actual_hex != expected_hex:
        result.fail(
            f"content hash mismatch: manifest says {expected_hex[:16]}..., "
            f"SKILL.md hashes to {actual_hex[:16]}..."
        )

    return result


def validate_skill_content(skill_md: Path) -> CheckResult:
    """Run SKILL_CONTRACT validation on the SKILL.md file."""
    result = CheckResult("skill_contract")

    # No dir_name check -- promotion packages don't live in skills/<name>/ yet
    errors = validate_skill_md(skill_md, dir_name=None)
    for err in errors:
        result.fail(err)

    return result


def validate_name_collision(manifest: dict) -> CheckResult:
    """Check that the skill slug doesn't already exist in skills/."""
    result = CheckResult("name_collision")

    slug = manifest.get("skill", {}).get("slug", "")
    if not slug:
        result.fail("manifest.skill.slug is missing -- cannot check for collisions")
        return result

    is_update = manifest.get("claudna", {}).get("is_update", False)
    existing = SKILLS_DIR / slug

    if existing.is_dir():
        if is_update:
            result.warn(
                f"skill '{slug}' already exists in skills/ -- this is a version update"
            )
        else:
            result.fail(
                f"skill '{slug}' already exists in skills/ but claudna.is_update is false. "
                f"Set is_update to true for version updates, or use a different slug for new skills."
            )

    return result


def validate_criteria_thresholds(manifest: dict) -> CheckResult:
    """Verify criteria_snapshot meets promotion thresholds."""
    result = CheckResult("criteria_thresholds")

    criteria = manifest.get("criteria_snapshot", {})
    if not isinstance(criteria, dict):
        result.fail("criteria_snapshot is not an object")
        return result

    # Arena thresholds
    for field, minimum in ARENA_THRESHOLDS.items():
        value = criteria.get(field)
        if value is None:
            continue  # already caught by structure check
        if not isinstance(value, (int, float)):
            result.fail(
                f"criteria_snapshot.{field} must be numeric, got {type(value).__name__}"
            )
            continue
        if value < minimum:
            result.fail(f"criteria_snapshot.{field} = {value}, minimum is {minimum}")

    # Judge thresholds
    mean_conf = criteria.get("mean_judge_confidence")
    if isinstance(mean_conf, (int, float)):
        if mean_conf < JUDGE_THRESHOLDS["mean_judge_confidence"]:
            result.fail(
                f"criteria_snapshot.mean_judge_confidence = {mean_conf}, "
                f"minimum is {JUDGE_THRESHOLDS['mean_judge_confidence']}"
            )

    min_conf = criteria.get("min_battle_confidence")
    if isinstance(min_conf, (int, float)):
        if min_conf < JUDGE_THRESHOLDS["min_battle_confidence"]:
            result.fail(
                f"criteria_snapshot.min_battle_confidence = {min_conf}, "
                f"minimum is {JUDGE_THRESHOLDS['min_battle_confidence']}"
            )

    # Telemetry thresholds
    for field, minimum in TELEMETRY_THRESHOLDS.items():
        value = criteria.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            result.fail(
                f"criteria_snapshot.{field} must be numeric, got {type(value).__name__}"
            )
            continue
        if value < minimum:
            result.fail(f"criteria_snapshot.{field} = {value}, minimum is {minimum}")

    return result


def validate_battle_history(battle_history_path: Path) -> CheckResult:
    """Validate battle-history.json structure (optional file)."""
    result = CheckResult("battle_history")

    if not battle_history_path.is_file():
        result.warn("battle-history.json not present (optional for manual promotions)")
        return result

    try:
        data = json.loads(battle_history_path.read_text())
    except json.JSONDecodeError as e:
        result.fail(f"battle-history.json is not valid JSON: {e}")
        return result

    if not isinstance(data, dict):
        result.fail(
            f"battle-history.json root must be an object, got {type(data).__name__}"
        )
        return result

    for field in ("total_battles", "record", "elo_trajectory"):
        if field not in data:
            result.fail(f"battle-history.json missing required field: {field!r}")

    record = data.get("record", {})
    if isinstance(record, dict):
        for field in ("wins", "losses", "draws"):
            if field not in record:
                result.fail(f"battle-history.json record.{field} missing")

    trajectory = data.get("elo_trajectory", [])
    if isinstance(trajectory, list) and len(trajectory) > 0:
        last_entry = trajectory[-1]
        if isinstance(last_entry, dict):
            elo_after = last_entry.get("elo_after")
            if (
                isinstance(elo_after, (int, float))
                and elo_after < ARENA_THRESHOLDS["elo_rating"]
            ):
                result.fail(
                    f"final ELO in trajectory is {elo_after}, "
                    f"below promotion threshold of {ARENA_THRESHOLDS['elo_rating']}"
                )

        # Losing streak check: last 3 battles must include at least 1 win.
        # Spec: "Last 3" by completedAt DESC; trajectory is ordered chronologically,
        # so take the tail. Tie-break by id is inherent in the ordering.
        tail = trajectory[-3:] if len(trajectory) >= 3 else trajectory
        tail_outcomes = [b.get("outcome") for b in tail if isinstance(b, dict)]
        if len(tail_outcomes) >= 3 and "win" not in tail_outcomes:
            result.fail(
                f"active losing streak: last {len(tail_outcomes)} battles "
                f"have no wins ({tail_outcomes})"
            )

    return result


def validate_telemetry_summary(telemetry_path: Path) -> CheckResult:
    """Validate telemetry-summary.json structure (optional file)."""
    result = CheckResult("telemetry_summary")

    if not telemetry_path.is_file():
        result.warn(
            "telemetry-summary.json not present (optional for manual promotions)"
        )
        return result

    try:
        data = json.loads(telemetry_path.read_text())
    except json.JSONDecodeError as e:
        result.fail(f"telemetry-summary.json is not valid JSON: {e}")
        return result

    if not isinstance(data, dict):
        result.fail(
            f"telemetry-summary.json root must be an object, got {type(data).__name__}"
        )
        return result

    for field in ("period", "invocations", "success_rate", "distinct_users"):
        if field not in data:
            result.fail(f"telemetry-summary.json missing required field: {field!r}")

    period = data.get("period", {})
    if isinstance(period, dict):
        for field in ("from", "to"):
            if field not in period:
                result.fail(f"telemetry-summary.json period.{field} missing")

    # Cross-check telemetry values against thresholds
    invocations = data.get("invocations")
    if (
        isinstance(invocations, (int, float))
        and invocations < TELEMETRY_THRESHOLDS["invocations"]
    ):
        result.fail(
            f"telemetry invocations = {invocations}, minimum is {TELEMETRY_THRESHOLDS['invocations']}"
        )

    success_rate = data.get("success_rate")
    if (
        isinstance(success_rate, (int, float))
        and success_rate < TELEMETRY_THRESHOLDS["success_rate"]
    ):
        result.fail(
            f"telemetry success_rate = {success_rate}, minimum is {TELEMETRY_THRESHOLDS['success_rate']}"
        )

    distinct_users = data.get("distinct_users")
    if (
        isinstance(distinct_users, (int, float))
        and distinct_users < TELEMETRY_THRESHOLDS["distinct_users"]
    ):
        result.fail(
            f"telemetry distinct_users = {distinct_users}, minimum is {TELEMETRY_THRESHOLDS['distinct_users']}"
        )

    return result


def run_validation(package_dir: Path) -> list[CheckResult]:
    """Run all validation checks on a promotion package directory."""
    results: list[CheckResult] = []

    manifest_path = package_dir / "manifest.json"
    skill_md_path = package_dir / "SKILL.md"
    battle_path = package_dir / "battle-history.json"
    telemetry_path = package_dir / "telemetry-summary.json"

    # Check required files exist
    files_check = CheckResult("required_files")
    if not manifest_path.is_file():
        files_check.fail("manifest.json not found in package directory")
    if not skill_md_path.is_file():
        files_check.fail("SKILL.md not found in package directory")
    results.append(files_check)

    if not files_check.passed:
        return results

    # Load manifest
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        manifest_check = CheckResult("manifest_parse")
        manifest_check.fail(f"manifest.json is not valid JSON: {e}")
        results.append(manifest_check)
        return results

    # Run all checks
    results.append(validate_manifest_structure(manifest))
    results.append(validate_content_hash(manifest, skill_md_path))
    results.append(validate_skill_content(skill_md_path))
    results.append(validate_name_collision(manifest))
    results.append(validate_criteria_thresholds(manifest))
    results.append(validate_battle_history(battle_path))
    results.append(validate_telemetry_summary(telemetry_path))

    return results


def print_human_report(results: list[CheckResult], package_dir: Path):
    """Print a human-readable validation report."""
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    all_passed = all(r.passed for r in results)

    if all_passed:
        print(f"PASS: {package_dir.name} -- all {total} checks passed")
    else:
        print(f"FAIL: {package_dir.name} -- {passed}/{total} checks passed\n")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}")
        for err in r.errors:
            print(f"         error: {err}")
        for warn in r.warnings:
            print(f"         warn:  {warn}")

    if not all_passed:
        print("\nFix the errors above before submitting the promotion PR.")


def print_json_report(results: list[CheckResult], package_dir: Path):
    """Print a JSON validation report."""
    report = {
        "package": str(package_dir),
        "passed": all(r.passed for r in results),
        "checks": [r.to_dict() for r in results],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        },
    }
    print(json.dumps(report, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Claudosseum promotion package for clauDNA.",
    )
    parser.add_argument(
        "package_dir",
        type=Path,
        help="Path to the promotion package directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report instead of human-readable",
    )
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    if not package_dir.is_dir():
        print(f"FAIL: {args.package_dir} is not a directory", file=sys.stderr)
        return 2

    results = run_validation(package_dir)

    if args.json:
        print_json_report(results, package_dir)
    else:
        print_human_report(results, package_dir)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
