import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAILWAY_DIR = ROOT / "deploy" / "railway"


def _load(name: str) -> dict:
    return json.loads((RAILWAY_DIR / name).read_text(encoding="utf-8"))


def test_railway_configs_use_reviewed_dockerfile_builder() -> None:
    for name in (
        "api.railway.json",
        "frontend.railway.json",
        "worker.railway.json",
        "scheduler.railway.json",
    ):
        config = _load(name)
        assert config["$schema"] == "https://railway.com/railway.schema.json"
        assert config["build"]["builder"] == "DOCKERFILE"
        assert config["build"]["dockerfilePath"] == "Dockerfile"
        assert config["deploy"]["restartPolicyType"] == "ALWAYS"


def test_only_api_owns_predeploy_database_bootstrap() -> None:
    api = _load("api.railway.json")
    assert api["deploy"]["preDeployCommand"] == ["tractusmind-db bootstrap"]

    for name in (
        "frontend.railway.json",
        "worker.railway.json",
        "scheduler.railway.json",
    ):
        assert "preDeployCommand" not in _load(name)["deploy"]


def test_railway_healthchecks_match_application_contracts() -> None:
    api = _load("api.railway.json")
    frontend = _load("frontend.railway.json")

    assert api["deploy"]["healthcheckPath"] == "/health/ready"
    assert api["deploy"]["healthcheckTimeout"] == 300
    assert frontend["deploy"]["healthcheckPath"] == "/api/health"
    assert frontend["deploy"]["healthcheckTimeout"] == 180


def test_api_start_command_uses_railway_port_with_safe_fallback() -> None:
    command = _load("api.railway.json")["deploy"]["startCommand"]
    assert "${PORT:-8000}" in command
    assert "--proxy-headers" in command
    assert "--timeout-graceful-shutdown 30" in command


def test_worker_and_scheduler_start_commands_remain_single_process() -> None:
    worker = _load("worker.railway.json")["deploy"]["startCommand"]
    scheduler = _load("scheduler.railway.json")["deploy"]["startCommand"]

    assert "dramatiq app.workers.tasks --processes 1 --threads 1" in worker
    assert scheduler == "tractusmind-scheduler"
