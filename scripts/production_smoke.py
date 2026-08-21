#!/usr/bin/env python3
"""Authenticated smoke test for a deployed TractusMind Mission Control endpoint."""

from __future__ import annotations

import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.environ.get("TRACTUSMIND_PRODUCTION_URL", "").rstrip("/")
API_KEY = os.environ.get("TRACTUSMIND_PRODUCTION_SMOKE_API_KEY", "")
CA_FILE = os.environ.get("TRACTUSMIND_PRODUCTION_SMOKE_CA_FILE", "").strip()


def fail(message: str) -> None:
    raise RuntimeError(message)


def assert_dependency_health(body: object) -> None:
    if not isinstance(body, dict) or body.get("status") != "ok":
        fail(f"Production backend readiness is not ok: {body}")
    checks = body.get("checks")
    if not isinstance(checks, dict) or not all(
        checks.get(name) == "ok" for name in ("postgres", "redis", "qdrant")
    ):
        fail(f"Production dependency health is not green: {checks}")


def main() -> int:
    if not BASE_URL:
        fail("TRACTUSMIND_PRODUCTION_URL is required")
    parsed = urlparse(BASE_URL)
    if parsed.scheme != "https" or not parsed.netloc:
        fail("Production URL must be an absolute HTTPS URL")
    if not API_KEY.startswith("tm_"):
        fail("TRACTUSMIND_PRODUCTION_SMOKE_API_KEY must be a TractusMind API key")
    if CA_FILE and not Path(CA_FILE).is_file():
        fail(f"Production smoke CA file does not exist: {CA_FILE}")

    cookie_jar = http.cookiejar.CookieJar()
    context = ssl.create_default_context(cafile=CA_FILE or None)
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )

    def call(
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        expected: tuple[int, ...] = (200,),
        origin: str | None = None,
        fetch_site: str | None = None,
    ) -> tuple[int, object, dict[str, str]]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Origin"] = origin or BASE_URL
            headers["Sec-Fetch-Site"] = fetch_site or "same-origin"
        req = urllib.request.Request(
            f"{BASE_URL}{path}", data=data, method=method, headers=headers
        )
        try:
            with opener.open(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
                status = response.status
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            status = exc.code
            response_headers = {key.lower(): value for key, value in exc.headers.items()}
        if status not in expected:
            fail(f"{method} {path} -> {status}: {raw[:1000]}")
        try:
            body: object = json.loads(raw) if raw else ""
        except json.JSONDecodeError:
            body = raw
        return status, body, response_headers

    print("[prod-smoke] checking TLS edge and security headers")
    _, _, headers = call("/")
    required_headers = {
        "strict-transport-security": "max-age=31536000",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "content-security-policy": "default-src 'self'",
    }
    for name, fragment in required_headers.items():
        value = headers.get(name, "")
        if fragment.lower() not in value.lower():
            fail(f"Missing/invalid {name}: {value!r}")
    if "server" in headers or "x-powered-by" in headers:
        fail("Production response exposes a server technology header")

    print("[prod-smoke] checking Mission Control runtime and real backend readiness")
    _, ui_health, _ = call("/api/health")
    if not isinstance(ui_health, dict) or ui_health.get("status") != "ok":
        fail(f"Mission Control runtime health is not ok: {ui_health}")
    _, backend_health, _ = call("/api/backend/health/ready")
    assert_dependency_health(backend_health)

    print("[prod-smoke] verifying browser mutation boundary rejects cross-site requests")
    call(
        "/api/session",
        method="POST",
        payload={"token": API_KEY},
        expected=(403,),
        origin="https://cross-site.invalid",
        fetch_site="cross-site",
    )

    print("[prod-smoke] authenticating through the real Mission Control session boundary")
    _, identity, session_headers = call(
        "/api/session", method="POST", payload={"token": API_KEY}
    )
    if not isinstance(identity, dict) or not identity.get("user_id"):
        fail(f"Unexpected production identity: {identity}")
    set_cookie = session_headers.get("set-cookie", "")
    required_cookie_fragments = (
        "__Host-tm_session=",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
        "Path=/",
    )
    for fragment in required_cookie_fragments:
        if fragment.lower() not in set_cookie.lower():
            fail(f"Production session cookie is missing {fragment!r}: {set_cookie!r}")

    print("[prod-smoke] checking authenticated session and product surfaces")
    call("/api/session")
    call("/overview")
    call("/sources")
    role = identity.get("role")
    if role in {"operator", "admin"}:
        call("/api/backend/v1/ops/summary")
        call("/api/backend/v1/ops/sources")
    if role == "admin":
        call("/api/backend/v1/ops/users")

    print("[prod-smoke] logging out")
    call("/api/session", method="DELETE", payload={})
    call("/api/session", expected=(401,))

    print("[prod-smoke] PRODUCTION ENDPOINT: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"[prod-smoke] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
