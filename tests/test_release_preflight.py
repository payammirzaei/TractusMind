from pathlib import Path

import pytest

from scripts import release_preflight

BASE_CONFIG = """\
version = 1

[contracts]
max_unsafe_answer_rate = 0.0
max_unsafe_evidence_accept_rate = 0.0
require_all_reviewed_regressions = true

[calibration]
threshold_tolerance = 0.000001
"""


def write_quality_gate(root: Path, content: str) -> None:
    path = root / "config" / "quality_gate.toml"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")


def test_release_preflight_rejects_unpinned_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_quality_gate(tmp_path, BASE_CONFIG)
    monkeypatch.setattr(release_preflight, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="minimum_relevance_score is not pinned"):
        release_preflight.validate_quality_gate()


def test_release_preflight_accepts_measured_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_quality_gate(tmp_path, BASE_CONFIG + "minimum_relevance_score = 0.423500\n")
    monkeypatch.setattr(release_preflight, "ROOT", tmp_path)

    assert release_preflight.validate_quality_gate() == pytest.approx(0.4235)


def test_release_preflight_rejects_unsafe_contract_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_quality_gate(
        tmp_path,
        BASE_CONFIG.replace("max_unsafe_answer_rate = 0.0", "max_unsafe_answer_rate = 0.01"),
    )
    monkeypatch.setattr(release_preflight, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="max_unsafe_answer_rate"):
        release_preflight.validate_quality_gate()
