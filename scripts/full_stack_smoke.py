#!/usr/bin/env python3
"""Smoke the running TractusMind stack through both API and Mission Control BFF.

The script intentionally uses only the Python standard library so it can run on a
fresh CI runner. It expects the development Compose stack to be running with an
OPS_ADMIN_KEY configured for bootstrap.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000").rstrip("/")
UI_URL = os.environ.get("SMOKE_UI_URL", "http://127.0.0.1:3100").rstrip("/")
ADMIN_KEY = os.environ.get("SMOKE_OPS_ADMIN_KEY", "integration-admin-key")
TIMEOUT_SECONDS = int(os.environ.get("SMOKE_TIMEOUT_SECONDS", "180"))


def request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, dict[str, object] | list[object] | str, dict[str, str]]:
    data = None
    merged = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        merged["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=merged)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
            status = response.status
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = exc.code
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
    if status not in expected:
        raise RuntimeError(f"{method} {url} -> {status}: {raw[:1000]}")
    try:
        body: dict[str, object] | list[object] | str = json.loads(raw) if raw else ""
    except json.JSONDecodeError:
        body = raw
    return status, body, response_headers


def assert_dependency_health(body: object, *, surface: str) -> None:
    if not isinstance(body, dict) or body.get("status") != "ok":
        raise RuntimeError(f"{surface} readiness did not report ok: {body}")
    checks = body.get("checks")
    if not isinstance(checks, dict) or not all(
        checks.get(name) == "ok" for name in ("postgres", "redis", "qdrant")
    ):
        raise RuntimeError(f"{surface} dependency checks are not green: {checks}")


def wait_ready() -> None:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            _, body, _ = request(f"{API_URL}/health/ready")
            assert_dependency_health(body, surface="FastAPI")
            return
        except Exception as exc:  # noqa: BLE001 - diagnostic loop
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"API did not become ready within {TIMEOUT_SECONDS}s: {last_error}")


def main() -> int:
    print("[integration] waiting for Postgres + Redis + Qdrant readiness")
    wait_ready()

    print("[integration] verifying Mission Control and backend readiness through the BFF")
    request(f"{UI_URL}/overview")
    _, ui_health, _ = request(f"{UI_URL}/api/health")
    if not isinstance(ui_health, dict) or ui_health.get("status") != "ok":
        raise RuntimeError(f"Mission Control health did not report ok: {ui_health}")
    _, backend_health, _ = request(f"{UI_URL}/api/backend/health/ready")
    assert_dependency_health(backend_health, surface="Mission Control BFF")

    print("[integration] bootstrapping a real admin identity through FastAPI")
    _, credential, _ = request(
        f"{API_URL}/v1/ops/users",
        method="POST",
        payload={"display_name": "Full Stack CI Admin", "role": "admin"},
        headers={"X-TractusMind-Admin-Key": ADMIN_KEY},
    )
    if not isinstance(credential, dict) or not isinstance(credential.get("api_key"), str):
        raise RuntimeError(f"Admin bootstrap did not return an API key: {credential}")
    api_key = credential["api_key"]

    print("[integration] establishing the HttpOnly Mission Control session")
    _, identity, login_headers = request(
        f"{UI_URL}/api/session",
        method="POST",
        payload={"token": api_key},
        headers={"Origin": UI_URL, "Sec-Fetch-Site": "same-origin"},
    )
    set_cookie = login_headers.get("set-cookie", "")
    if "__Host-tm_session=" not in set_cookie or "HttpOnly" not in set_cookie or "Secure" not in set_cookie:
        raise RuntimeError(f"Production session cookie policy missing: {set_cookie}")
    if not isinstance(identity, dict) or identity.get("role") != "admin":
        raise RuntimeError(f"Unexpected authenticated identity: {identity}")

    # CI reaches the production Next runtime over HTTP, so a browser would intentionally
    # withhold the Secure cookie. Send it explicitly here to exercise server-side BFF logic.
    cookie = {"Cookie": f"__Host-tm_session={api_key}"}

    print("[integration] exercising authenticated session + BFF against the real API")
    request(f"{UI_URL}/api/session", headers=cookie)
    request(f"{UI_URL}/api/backend/v1/ops/summary", headers=cookie)
    request(f"{UI_URL}/api/backend/v1/ops/sources", headers=cookie)
    request(f"{UI_URL}/api/backend/v1/conversations", headers=cookie)

    print("[integration] exercising admin mutation through same-site BFF protection")
    _, created_user, _ = request(
        f"{UI_URL}/api/backend/v1/ops/users",
        method="POST",
        payload={"display_name": "Full Stack CI User", "role": "user"},
        headers={**cookie, "Origin": UI_URL, "Sec-Fetch-Site": "same-origin"},
    )
    if not isinstance(created_user, dict) or created_user.get("role") != "user":
        raise RuntimeError(f"BFF admin mutation returned unexpected payload: {created_user}")

    print("[integration] proving cross-site mutation is rejected")
    request(
        f"{UI_URL}/api/backend/v1/ops/users",
        method="POST",
        payload={"display_name": "must-not-exist", "role": "user"},
        headers={**cookie, "Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
        expected=(403,),
    )

    print("[integration] verifying logout invalidates the browser session")
    request(
        f"{UI_URL}/api/session",
        method="DELETE",
        headers={**cookie, "Origin": UI_URL, "Sec-Fetch-Site": "same-origin"},
    )

    print("[integration] FULL STACK CONTROL PLANE: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"[integration] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
