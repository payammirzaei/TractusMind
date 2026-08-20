const baseUrl = (process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const routes = ["/", "/overview", "/sources", "/ops", "/quality", "/admin"];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForServer() {
  let lastError;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/api/health`, { cache: "no-store" });
      if (response.ok) return;
      lastError = new Error(`health returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw lastError ?? new Error("Mission Control did not become ready");
}

function verifySecurityHeaders(response, route) {
  assert(response.headers.get("x-content-type-options") === "nosniff", `${route} missing nosniff`);
  assert(response.headers.get("x-frame-options") === "DENY", `${route} missing frame denial`);
  assert(response.headers.get("referrer-policy") === "no-referrer", `${route} missing referrer policy`);
  assert((response.headers.get("permissions-policy") ?? "").includes("camera=()"), `${route} missing permissions policy`);
  assert(response.headers.get("cross-origin-opener-policy") === "same-origin", `${route} missing COOP`);
  assert(response.headers.get("cross-origin-resource-policy") === "same-origin", `${route} missing CORP`);
  assert(response.headers.get("x-powered-by") == null, `${route} exposes X-Powered-By`);
  const csp = response.headers.get("content-security-policy") ?? "";
  assert(csp.includes("default-src 'self'"), `${route} missing default-src CSP`);
  assert(csp.includes("frame-ancestors 'none'"), `${route} missing frame-ancestors CSP`);
  assert(csp.includes("connect-src 'self'"), `${route} missing connect-src CSP`);
}

async function probeRoute(route) {
  const response = await fetch(`${baseUrl}${route}`, {
    cache: "no-store",
    redirect: "manual",
  });
  if (response.status !== 200) {
    throw new Error(`${route} returned ${response.status}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/html")) {
    throw new Error(`${route} returned unexpected content-type: ${contentType}`);
  }
  verifySecurityHeaders(response, route);
  await response.arrayBuffer();
  process.stdout.write(`ok ${route}\n`);
}

await waitForServer();

const healthResponse = await fetch(`${baseUrl}/api/health`, { cache: "no-store" });
const health = await healthResponse.json();
if (!healthResponse.ok || health.status !== "ok") {
  throw new Error(`/api/health failed: ${healthResponse.status} ${JSON.stringify(health)}`);
}
process.stdout.write("ok /api/health\n");

for (const route of routes) {
  await probeRoute(route);
}

const missing = await fetch(`${baseUrl}/surface-that-does-not-exist`, { redirect: "manual" });
assert(missing.status === 404, `not-found route returned ${missing.status}`);
verifySecurityHeaders(missing, "404 surface");
process.stdout.write("ok themed 404 surface\n");

process.stdout.write(`Mission Control smoke passed (${routes.length + 2} routes).\n`);
