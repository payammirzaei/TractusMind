import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GateViolation:
    check: str
    detail: str


@dataclass(frozen=True)
class GateConfig:
    max_unsafe_answer_rate: float
    max_unsafe_evidence_accept_rate: float
    require_all_reviewed_regressions: bool
    minimum_relevance_score: float | None
    threshold_tolerance: float


def load_gate_config(path: Path) -> GateConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    contracts = raw.get("contracts", {})
    calibration = raw.get("calibration", {})
    threshold = calibration.get("minimum_relevance_score")
    return GateConfig(
        max_unsafe_answer_rate=float(contracts.get("max_unsafe_answer_rate", 0.0)),
        max_unsafe_evidence_accept_rate=float(
            contracts.get("max_unsafe_evidence_accept_rate", 0.0)
        ),
        require_all_reviewed_regressions=bool(
            contracts.get("require_all_reviewed_regressions", True)
        ),
        minimum_relevance_score=(float(threshold) if threshold is not None else None),
        threshold_tolerance=float(calibration.get("threshold_tolerance", 1e-6)),
    )


def _load_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_calibration(
    report: dict[str, object],
    config: GateConfig,
    *,
    require_pinned_threshold: bool,
) -> list[GateViolation]:
    violations: list[GateViolation] = []
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        return [GateViolation("calibration-report", "missing metrics object")]

    unsafe_rate = float(metrics.get("unsafe_evidence_accept_rate", 1.0))
    if unsafe_rate > config.max_unsafe_evidence_accept_rate:
        violations.append(
            GateViolation(
                "unsafe-evidence-accept-rate",
                f"{unsafe_rate:.6f} exceeds {config.max_unsafe_evidence_accept_rate:.6f}",
            )
        )

    recommended = report.get("recommended_threshold")
    if not isinstance(recommended, int | float):
        violations.append(
            GateViolation("calibration-threshold", "missing recommended_threshold")
        )
        return violations

    if config.minimum_relevance_score is None:
        if require_pinned_threshold:
            violations.append(
                GateViolation(
                    "pinned-threshold",
                    "calibration is safe but no measured minimum_relevance_score is pinned",
                )
            )
        return violations

    if abs(float(recommended) - config.minimum_relevance_score) > config.threshold_tolerance:
        violations.append(
            GateViolation(
                "threshold-drift",
                "recommended threshold "
                f"{float(recommended):.6f} differs from pinned "
                f"{config.minimum_relevance_score:.6f}",
            )
        )
    return violations


def _gate_answer_report(
    report: dict[str, object],
    config: GateConfig,
    *,
    require_all_cases: bool,
    label: str,
) -> list[GateViolation]:
    violations: list[GateViolation] = []
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        return [GateViolation(f"{label}-report", "missing metrics object")]

    unsafe_rate = float(metrics.get("unsafe_answer_rate", 1.0))
    if unsafe_rate > config.max_unsafe_answer_rate:
        violations.append(
            GateViolation(
                f"{label}-unsafe-answer-rate",
                f"{unsafe_rate:.6f} exceeds {config.max_unsafe_answer_rate:.6f}",
            )
        )

    if not require_all_cases:
        return violations

    details = report.get("details")
    if not isinstance(details, list) or not details:
        violations.append(GateViolation(f"{label}-cases", "no regression cases evaluated"))
        return violations

    failed = [
        str(detail.get("id", "unknown"))
        for detail in details
        if isinstance(detail, dict) and not bool(detail.get("correct"))
    ]
    if failed:
        violations.append(
            GateViolation(
                f"{label}-regressions",
                "reviewed answer regressions failed: " + ", ".join(failed),
            )
        )
    return violations


def _gate_retrieval_report(
    report: dict[str, object],
    *,
    label: str,
) -> list[GateViolation]:
    reports = report.get("reports")
    if not isinstance(reports, list) or len(reports) != 1:
        return [
            GateViolation(
                f"{label}-report",
                "regression gate expects exactly one benchmark mode report",
            )
        ]
    mode_report = reports[0]
    if not isinstance(mode_report, dict):
        return [GateViolation(f"{label}-report", "invalid benchmark report")]
    details = mode_report.get("details")
    if not isinstance(details, list) or not details:
        return [GateViolation(f"{label}-cases", "no regression cases evaluated")]

    failed = [
        str(detail.get("id", "unknown"))
        for detail in details
        if isinstance(detail, dict) and not bool(detail.get("hit"))
    ]
    if failed:
        return [
            GateViolation(
                f"{label}-regressions",
                "reviewed retrieval regressions failed: " + ", ".join(failed),
            )
        ]
    return []


def evaluate_gate(
    *,
    config: GateConfig,
    calibration_report: dict[str, object] | None = None,
    answer_report: dict[str, object] | None = None,
    retrieval_regression_report: dict[str, object] | None = None,
    debug_regression_report: dict[str, object] | None = None,
    answer_regression_report: dict[str, object] | None = None,
    require_pinned_threshold: bool = False,
) -> list[GateViolation]:
    violations: list[GateViolation] = []
    if calibration_report is not None:
        violations.extend(
            _gate_calibration(
                calibration_report,
                config,
                require_pinned_threshold=require_pinned_threshold,
            )
        )
    if answer_report is not None:
        violations.extend(
            _gate_answer_report(
                answer_report,
                config,
                require_all_cases=False,
                label="answer",
            )
        )
    if config.require_all_reviewed_regressions:
        if retrieval_regression_report is not None:
            violations.extend(
                _gate_retrieval_report(
                    retrieval_regression_report,
                    label="retrieval",
                )
            )
        if debug_regression_report is not None:
            violations.extend(
                _gate_retrieval_report(
                    debug_regression_report,
                    label="debug",
                )
            )
        if answer_regression_report is not None:
            violations.extend(
                _gate_answer_report(
                    answer_regression_report,
                    config,
                    require_all_cases=True,
                    label="answer-regression",
                )
            )
    return violations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-quality-gate")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/quality_gate.toml"),
    )
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--answer", type=Path)
    parser.add_argument("--retrieval-regression", type=Path)
    parser.add_argument("--debug-regression", type=Path)
    parser.add_argument("--answer-regression", type=Path)
    parser.add_argument("--require-pinned-threshold", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    config = load_gate_config(args.config)
    violations = evaluate_gate(
        config=config,
        calibration_report=_load_report(args.calibration) if args.calibration else None,
        answer_report=_load_report(args.answer) if args.answer else None,
        retrieval_regression_report=(
            _load_report(args.retrieval_regression)
            if args.retrieval_regression
            else None
        ),
        debug_regression_report=(
            _load_report(args.debug_regression) if args.debug_regression else None
        ),
        answer_regression_report=(
            _load_report(args.answer_regression) if args.answer_regression else None
        ),
        require_pinned_threshold=args.require_pinned_threshold,
    )
    payload = {
        "passed": not violations,
        "violations": [violation.__dict__ for violation in violations],
        "pinned_minimum_relevance_score": config.minimum_relevance_score,
    }
    print(json.dumps(payload, indent=2))
    if violations:
        sys.exit(1)


if __name__ == "__main__":
    main()
