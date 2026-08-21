import tomllib
from pathlib import Path


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _number(mapping: dict[str, object], key: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def evaluate_performance_budget(
    report: dict[str, object],
    budget_path: Path,
) -> tuple[dict[str, object], list[str]]:
    config = tomllib.loads(budget_path.read_text(encoding="utf-8"))
    expected_workload = _mapping(config.get("workload"), "workload")
    budget = _mapping(config.get("budget"), "budget")

    environment = _mapping(report.get("environment"), "report.environment")
    workload = _mapping(report.get("workload"), "report.workload")
    steady = _mapping(report.get("steady_state"), "report.steady_state")

    dense = _mapping(steady.get("dense_query"), "report.steady_state.dense_query")
    sparse = _mapping(steady.get("sparse_query"), "report.steady_state.sparse_query")
    rerank = _mapping(steady.get("rerank"), "report.steady_state.rerank")
    combined = _mapping(
        steady.get("combined_model_compute"),
        "report.steady_state.combined_model_compute",
    )

    affinity = environment.get("cpu_affinity")
    if not isinstance(affinity, list) or not affinity:
        raise ValueError("report.environment.cpu_affinity must be a non-empty list")

    violations: list[str] = []
    workload_checks = {
        "cpu_affinity_count": {
            "observed": len(affinity),
            "limit": int(_number(expected_workload, "cpu_count")),
            "passed": len(affinity) <= int(_number(expected_workload, "cpu_count")),
        },
        "candidate_count": {
            "observed": int(_number(workload, "candidates_per_query")),
            "expected": int(_number(expected_workload, "candidate_count")),
        },
        "candidate_chars": {
            "observed": int(_number(workload, "candidate_chars")),
            "expected": int(_number(expected_workload, "candidate_chars")),
        },
        "rerank_limit": {
            "observed": int(_number(workload, "rerank_limit")),
            "expected": int(_number(expected_workload, "rerank_limit")),
        },
    }

    if not workload_checks["cpu_affinity_count"]["passed"]:
        violations.append(
            "CPU affinity exceeded the certified workload: "
            f"{len(affinity)} > {int(_number(expected_workload, 'cpu_count'))}"
        )

    for key in ("candidate_count", "candidate_chars", "rerank_limit"):
        check = workload_checks[key]
        passed = check["observed"] == check["expected"]
        check["passed"] = passed
        if not passed:
            violations.append(
                f"Workload mismatch for {key}: {check['observed']} != {check['expected']}"
            )

    observed = {
        "dense_query_p95_ms": _number(dense, "p95_ms"),
        "sparse_query_p95_ms": _number(sparse, "p95_ms"),
        "rerank_p95_ms": _number(rerank, "p95_ms"),
        "combined_model_compute_p95_ms": _number(combined, "p95_ms"),
        "max_rss_mb": _number(environment, "max_rss_mb"),
    }
    budget_checks: dict[str, dict[str, float | bool]] = {}
    for key, value in observed.items():
        limit = _number(budget, key)
        passed = value <= limit
        budget_checks[key] = {
            "observed": value,
            "limit": limit,
            "passed": passed,
        }
        if not passed:
            violations.append(f"{key} exceeded budget: {value:.3f} > {limit:.3f}")

    return (
        {
            "config": str(budget_path),
            "status": "pass" if not violations else "fail",
            "workload_checks": workload_checks,
            "budget_checks": budget_checks,
        },
        violations,
    )
