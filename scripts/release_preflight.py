#!/usr/bin/env python3
"""Fail-closed release readiness checks for TractusMind tags."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        fail(f"required file is missing: {path.relative_to(ROOT)}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate_quality_gate() -> float:
    config = load_toml(ROOT / "config" / "quality_gate.toml")
    if config.get("version") != 1:
        fail("config/quality_gate.toml must use version = 1")

    contracts = config.get("contracts")
    if not isinstance(contracts, dict):
        fail("quality gate contracts are missing")
    if contracts.get("max_unsafe_answer_rate") != 0.0:
        fail("max_unsafe_answer_rate must remain 0.0 for v1")
    if contracts.get("max_unsafe_evidence_accept_rate") != 0.0:
        fail("max_unsafe_evidence_accept_rate must remain 0.0 for v1")
    if contracts.get("require_all_reviewed_regressions") is not True:
        fail("all reviewed regressions must be required for v1")

    calibration = config.get("calibration")
    if not isinstance(calibration, dict):
        fail("quality gate calibration section is missing")
    threshold = calibration.get("minimum_relevance_score")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        fail(
            "minimum_relevance_score is not pinned; run full-corpus calibration "
            "and human-review its measured candidate before releasing"
        )
    threshold_value = float(threshold)
    if not 0.0 < threshold_value <= 1.0:
        fail("minimum_relevance_score must be within (0, 1]")

    tolerance = calibration.get("threshold_tolerance")
    if not isinstance(tolerance, (int, float)) or not 0.0 < float(tolerance) <= 0.001:
        fail("threshold_tolerance must be a small positive numeric value")
    return threshold_value


def validate_sources() -> int:
    registry = load_toml(ROOT / "config" / "sources.toml")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        fail("config/sources.toml does not contain a source registry")
    enabled = [item for item in sources if isinstance(item, dict) and item.get("enabled") is True]
    if len(enabled) != 6:
        fail(f"v1 requires exactly six enabled Tractus-X sources; found {len(enabled)}")
    required_fields = {"id", "provider", "owner", "repo", "ref", "component"}
    for source in enabled:
        missing = sorted(required_fields.difference(source))
        if missing:
            fail(f"source {source.get('id', '<unknown>')} misses fields: {', '.join(missing)}")
    return len(enabled)


def validate_production_files() -> None:
    required = (
        "docker-compose.prod.yml",
        "docker-compose.ui.prod.yml",
        "config/Caddyfile.ui.prod",
        "scripts/production_smoke.py",
        ".github/workflows/production-runtime.yml",
        ".github/workflows/backup-restore.yml",
        ".github/workflows/quality-gate.yml",
        ".github/workflows/full-corpus-validation.yml",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"release-critical file is missing: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    threshold = validate_quality_gate()
    source_count = validate_sources()
    validate_production_files()

    print("TractusMind release preflight: PASS")
    print(f"  calibrated threshold: {threshold:.6f}")
    print(f"  enabled sources: {source_count}")
    print("  production topology: present")
    print("  backup/restore proof workflow: present")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - release CLI boundary
        print(f"TractusMind release preflight: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
