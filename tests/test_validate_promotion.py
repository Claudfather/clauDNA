"""Unit tests for validate-promotion-package.py.

Tests boundary conditions for each validation check using the fixtures
in tests/fixtures/.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path


# Add scripts/ to path so skill_checks is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Import the hyphenated module via importlib
_spec = importlib.util.spec_from_file_location(
    "validate_promotion_package",
    REPO_ROOT / "scripts" / "validate-promotion-package.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

TELEMETRY_THRESHOLDS = _mod.TELEMETRY_THRESHOLDS
run_validation = _mod.run_validation
validate_battle_history = _mod.validate_battle_history
validate_content_hash = _mod.validate_content_hash
validate_criteria_thresholds = _mod.validate_criteria_thresholds
validate_manifest_structure = _mod.validate_manifest_structure
validate_name_collision = _mod.validate_name_collision
validate_skill_content = _mod.validate_skill_content
validate_telemetry_summary = _mod.validate_telemetry_summary

FIXTURES = REPO_ROOT / "tests" / "fixtures"
VALID_PKG = FIXTURES / "valid-package"
FAILING_PKG = FIXTURES / "failing-package"


# --- Helpers ---


def load_manifest(pkg_dir: Path) -> dict:
    return json.loads((pkg_dir / "manifest.json").read_text())


def make_temp_package(base_pkg: Path) -> Path:
    """Copy a fixture package to a temp dir for mutation tests."""
    tmp = Path(tempfile.mkdtemp())
    dst = tmp / "pkg"
    shutil.copytree(base_pkg, dst)
    return dst


# --- Valid package (all checks should pass) ---


class TestValidPackage:
    def test_all_checks_pass(self):
        results = run_validation(VALID_PKG)
        failures = [r for r in results if not r.passed]
        assert failures == [], f"Unexpected failures: {[r.to_dict() for r in failures]}"

    def test_exit_code_zero(self):
        results = run_validation(VALID_PKG)
        assert all(r.passed for r in results)


# --- Failing package (multiple checks should fail) ---


class TestFailingPackage:
    def test_has_failures(self):
        results = run_validation(FAILING_PKG)
        assert not all(r.passed for r in results)

    def test_criteria_fail(self):
        results = run_validation(FAILING_PKG)
        criteria = next(r for r in results if r.name == "criteria_thresholds")
        assert not criteria.passed
        # ELO, battles, win_rate, confidence, telemetry should all fail
        assert len(criteria.errors) >= 5

    def test_content_hash_fails(self):
        results = run_validation(FAILING_PKG)
        hash_check = next(r for r in results if r.name == "content_hash")
        assert not hash_check.passed

    def test_skill_contract_fails(self):
        results = run_validation(FAILING_PKG)
        skill_check = next(r for r in results if r.name == "skill_contract")
        assert not skill_check.passed
        # description too short + body too short
        error_text = " ".join(skill_check.errors)
        assert "too short" in error_text


# --- Manifest structure ---


class TestManifestStructure:
    def test_missing_sections(self):
        result = validate_manifest_structure({})
        assert not result.passed
        # At minimum, all 5 top-level keys should be reported missing
        top_level_errors = [e for e in result.errors if "top-level key" in e]
        assert len(top_level_errors) == 5

    def test_bad_datetime(self):
        manifest = load_manifest(VALID_PKG)
        manifest["promotion"]["promoted_at"] = "not-a-date"
        result = validate_manifest_structure(manifest)
        assert not result.passed
        assert any("ISO datetime" in e for e in result.errors)

    def test_missing_skill_fields(self):
        manifest = load_manifest(VALID_PKG)
        del manifest["skill"]["content_hash"]
        result = validate_manifest_structure(manifest)
        assert not result.passed
        assert any("content_hash" in e for e in result.errors)

    def test_missing_category_fields(self):
        manifest = load_manifest(VALID_PKG)
        del manifest["skill"]["category"]["domain"]
        result = validate_manifest_structure(manifest)
        assert not result.passed

    def test_bad_hash_prefix(self):
        manifest = load_manifest(VALID_PKG)
        manifest["skill"]["content_hash"] = "md5:abc123"
        result = validate_manifest_structure(manifest)
        assert not result.passed
        assert any("sha256:" in e for e in result.errors)


# --- Content hash ---


class TestContentHash:
    def test_valid_hash(self):
        manifest = load_manifest(VALID_PKG)
        result = validate_content_hash(manifest, VALID_PKG / "SKILL.md")
        assert result.passed

    def test_hash_mismatch(self):
        manifest = load_manifest(VALID_PKG)
        manifest["skill"]["content_hash"] = (
            "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
        result = validate_content_hash(manifest, VALID_PKG / "SKILL.md")
        assert not result.passed
        assert any("mismatch" in e for e in result.errors)

    def test_missing_hash(self):
        result = validate_content_hash({"skill": {}}, VALID_PKG / "SKILL.md")
        assert not result.passed

    def test_bad_prefix(self):
        result = validate_content_hash(
            {"skill": {"content_hash": "md5:abc"}},
            VALID_PKG / "SKILL.md",
        )
        assert not result.passed


# --- Criteria thresholds ---


class TestCriteriaThresholds:
    def test_passing_criteria(self):
        manifest = load_manifest(VALID_PKG)
        result = validate_criteria_thresholds(manifest)
        assert result.passed

    def test_elo_boundary(self):
        manifest = load_manifest(VALID_PKG)
        # Exactly at threshold should pass
        manifest["criteria_snapshot"]["elo_rating"] = 1400
        result = validate_criteria_thresholds(manifest)
        elo_errors = [e for e in result.errors if "elo_rating" in e]
        assert len(elo_errors) == 0

        # One below should fail
        manifest["criteria_snapshot"]["elo_rating"] = 1399
        result = validate_criteria_thresholds(manifest)
        assert not result.passed
        assert any("elo_rating" in e for e in result.errors)

    def test_win_rate_boundary(self):
        manifest = load_manifest(VALID_PKG)
        manifest["criteria_snapshot"]["win_rate"] = 0.60
        result = validate_criteria_thresholds(manifest)
        wr_errors = [e for e in result.errors if "win_rate" in e]
        assert len(wr_errors) == 0

        manifest["criteria_snapshot"]["win_rate"] = 0.59
        result = validate_criteria_thresholds(manifest)
        assert any("win_rate" in e for e in result.errors)

    def test_judge_confidence_boundary(self):
        manifest = load_manifest(VALID_PKG)
        manifest["criteria_snapshot"]["mean_judge_confidence"] = 65
        result = validate_criteria_thresholds(manifest)
        conf_errors = [e for e in result.errors if "mean_judge_confidence" in e]
        assert len(conf_errors) == 0

        manifest["criteria_snapshot"]["mean_judge_confidence"] = 64
        result = validate_criteria_thresholds(manifest)
        assert any("mean_judge_confidence" in e for e in result.errors)

    def test_min_battle_confidence_boundary(self):
        manifest = load_manifest(VALID_PKG)
        manifest["criteria_snapshot"]["min_battle_confidence"] = 40
        result = validate_criteria_thresholds(manifest)
        assert all("min_battle_confidence" not in e for e in result.errors)

        manifest["criteria_snapshot"]["min_battle_confidence"] = 39
        result = validate_criteria_thresholds(manifest)
        assert any("min_battle_confidence" in e for e in result.errors)

    def test_telemetry_boundaries(self):
        manifest = load_manifest(VALID_PKG)
        for field, minimum in TELEMETRY_THRESHOLDS.items():
            manifest["criteria_snapshot"][field] = minimum
        result = validate_criteria_thresholds(manifest)
        assert result.passed

    def test_non_numeric_value(self):
        manifest = load_manifest(VALID_PKG)
        manifest["criteria_snapshot"]["elo_rating"] = "high"
        result = validate_criteria_thresholds(manifest)
        assert not result.passed
        assert any("numeric" in e for e in result.errors)


# --- Name collision ---


class TestNameCollision:
    def test_no_collision_new_skill(self):
        manifest = load_manifest(VALID_PKG)
        # example-review doesn't exist in skills/
        result = validate_name_collision(manifest)
        assert result.passed

    def test_collision_detected(self):
        manifest = load_manifest(VALID_PKG)
        # Use a slug that exists in skills/
        manifest["skill"]["slug"] = "tech-debt"
        manifest["claudna"]["is_update"] = False
        result = validate_name_collision(manifest)
        assert not result.passed

    def test_collision_allowed_for_updates(self):
        manifest = load_manifest(VALID_PKG)
        manifest["skill"]["slug"] = "tech-debt"
        manifest["claudna"]["is_update"] = True
        result = validate_name_collision(manifest)
        assert result.passed  # passes with a warning
        assert len(result.warnings) > 0


# --- Battle history ---


class TestBattleHistory:
    def test_valid_history(self):
        result = validate_battle_history(VALID_PKG / "battle-history.json")
        assert result.passed

    def test_missing_file_is_warning(self):
        result = validate_battle_history(Path("/nonexistent/battle-history.json"))
        assert result.passed  # optional file
        assert len(result.warnings) > 0

    def test_bad_json(self):
        pkg = make_temp_package(VALID_PKG)
        try:
            (pkg / "battle-history.json").write_text("not json")
            result = validate_battle_history(pkg / "battle-history.json")
            assert not result.passed
        finally:
            shutil.rmtree(pkg.parent)

    def test_low_final_elo(self):
        result = validate_battle_history(FAILING_PKG / "battle-history.json")
        assert not result.passed
        assert any("final ELO" in e for e in result.errors)

    def test_missing_record_fields(self):
        pkg = make_temp_package(VALID_PKG)
        try:
            data = json.loads((pkg / "battle-history.json").read_text())
            del data["record"]
            (pkg / "battle-history.json").write_text(json.dumps(data))
            result = validate_battle_history(pkg / "battle-history.json")
            assert not result.passed
        finally:
            shutil.rmtree(pkg.parent)

    def test_losing_streak_fails(self):
        result = validate_battle_history(FIXTURES / "losing-streak-history.json")
        assert not result.passed
        assert any("losing streak" in e for e in result.errors)

    def test_no_losing_streak_in_valid(self):
        # Valid package ends with a win — should not trigger streak check
        result = validate_battle_history(VALID_PKG / "battle-history.json")
        assert result.passed
        assert not any("losing streak" in e for e in result.errors)


# --- Telemetry summary ---


class TestTelemetrySummary:
    def test_valid_telemetry(self):
        result = validate_telemetry_summary(VALID_PKG / "telemetry-summary.json")
        assert result.passed

    def test_missing_file_is_warning(self):
        result = validate_telemetry_summary(Path("/nonexistent/telemetry-summary.json"))
        assert result.passed
        assert len(result.warnings) > 0

    def test_below_thresholds(self):
        result = validate_telemetry_summary(FAILING_PKG / "telemetry-summary.json")
        assert not result.passed
        assert len(result.errors) >= 3  # invocations, success_rate, distinct_users

    def test_missing_period(self):
        pkg = make_temp_package(VALID_PKG)
        try:
            data = json.loads((pkg / "telemetry-summary.json").read_text())
            del data["period"]
            (pkg / "telemetry-summary.json").write_text(json.dumps(data))
            result = validate_telemetry_summary(pkg / "telemetry-summary.json")
            assert not result.passed
        finally:
            shutil.rmtree(pkg.parent)


# --- SKILL.md content validation ---


class TestSkillContent:
    def test_valid_skill(self):
        result = validate_skill_content(VALID_PKG / "SKILL.md")
        assert result.passed

    def test_stub_skill_fails(self):
        result = validate_skill_content(FAILING_PKG / "SKILL.md")
        assert not result.passed

    def test_missing_skill_md(self):
        result = validate_skill_content(Path("/nonexistent/SKILL.md"))
        assert not result.passed


# --- Integration: full pipeline ---


class TestFullPipeline:
    def test_valid_package_end_to_end(self):
        results = run_validation(VALID_PKG)
        assert all(r.passed for r in results)
        assert len(results) >= 7  # all check categories

    def test_failing_package_end_to_end(self):
        results = run_validation(FAILING_PKG)
        failed = [r.name for r in results if not r.passed]
        # Should fail on hash, skill contract, criteria, battle history, telemetry
        assert "content_hash" in failed
        assert "skill_contract" in failed
        assert "criteria_thresholds" in failed

    def test_missing_manifest_aborts_early(self):
        pkg = make_temp_package(VALID_PKG)
        try:
            (pkg / "manifest.json").unlink()
            results = run_validation(pkg)
            assert not all(r.passed for r in results)
            # Should have only the required_files check
            assert len(results) == 1
        finally:
            shutil.rmtree(pkg.parent)

    def test_mutated_skill_md_fails_hash(self):
        pkg = make_temp_package(VALID_PKG)
        try:
            skill_md = pkg / "SKILL.md"
            skill_md.write_text(skill_md.read_text() + "\nExtra content appended.")
            results = run_validation(pkg)
            hash_check = next(r for r in results if r.name == "content_hash")
            assert not hash_check.passed
        finally:
            shutil.rmtree(pkg.parent)
