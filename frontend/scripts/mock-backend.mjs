import http from "node:http";

const host = "127.0.0.1";
const port = Number(process.env.MOCK_BACKEND_PORT ?? 8000);
const validToken = "tm_test_admin";

const identity = {
  user_id: "ci-admin",
  display_name: "CI Admin",
  role: "admin",
  auth_type: "api_key",
};

function json(response, status, payload) {
  response.writeHead(status, {
    "content-type": "application/json",
    "cache-control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

function authorized(request) {
  return request.headers.authorization === `Bearer ${validToken}`;
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);

  if (request.method === "GET" && url.pathname === "/health/ready") {
    return json(response, 200, { status: "ok", checks: { postgres: "ok", redis: "ok", qdrant: "ok" } });
  }

  if (!authorized(request)) {
    return json(response, 401, { detail: "Invalid test credential" });
  }

  if (request.method === "GET" && url.pathname === "/v1/me") {
    return json(response, 200, identity);
  }

  if (request.method === "GET" && url.pathname === "/v1/ops/summary") {
    return json(response, 200, {
      configured_sources: 1,
      enabled_sources: 1,
      indexed_sources: 1,
      locked_sources: 0,
      running_sources: 0,
      failed_sources: 0,
      scheduler_interval_seconds: 3600,
      redis_ok: true,
      run_status_counts: { succeeded: 1 },
    });
  }

  if (request.method === "GET" && url.pathname === "/v1/ops/sources") {
    return json(response, 200, [{
      source_id: "tractusx-sdk",
      repository: "eclipse-tractusx/tractusx-sdk",
      component: "Tractus-X SDK",
      priority: "high",
      enabled: true,
      configured_ref: "main",
      version_ref: "main",
      snapshot_commit_sha: "0123456789abcdef0123456789abcdef01234567",
      file_count: 42,
      updated_at: "2026-08-20T20:00:00Z",
      latest_run_status: "succeeded",
      latest_run_error: null,
      locked: false,
    }]);
  }

  if (request.method === "GET" && url.pathname === "/v1/ops/runs") {
    return json(response, 200, []);
  }

  if (request.method === "GET" && url.pathname === "/v1/ops/quality/summary") {
    return json(response, 200, { review_counts: { pending: 0, promoted: 1, dismissed: 0 }, regression_cases: 1 });
  }

  if (request.method === "GET" && url.pathname === "/v1/ops/quality/reviews") {
    return json(response, 200, []);
  }

  if (request.method === "POST" && url.pathname === "/v1/ops/sync") {
    return json(response, 202, { status: "queued", count: 1, jobs: [{ source_id: "tractusx-sdk", status: "queued", message_id: "ci-message" }] });
  }

  return json(response, 404, { detail: "Unknown mock endpoint" });
});

server.listen(port, host, () => {
  process.stdout.write(`mock backend listening on http://${host}:${port}\n`);
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
